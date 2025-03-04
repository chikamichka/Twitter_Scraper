from twikit import Client, TooManyRequests
import asyncio
from datetime import datetime
import csv
from configparser import ConfigParser
from random import randint, uniform
import os
import re
import nltk
from transformers import pipeline

# NLP setup
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

# Constants
MINIMUM_TWEETS = 1000
QUERY = '("#meal" OR "#diet" OR "#eating" OR "#junkfood" OR "#fastfood") lang:en -filter:retweets since:2020-01-01 until:2025-12-31'
REPLY_THRESHOLD = 5

# Rate limiting configuration
MIN_WAIT_BETWEEN_TWEETS = 30
MAX_WAIT_BETWEEN_TWEETS = 90
MIN_WAIT_BETWEEN_PAGES = 60
MAX_WAIT_BETWEEN_PAGES = 180
MAX_TWEETS_PER_SESSION = 100
SESSION_BREAK_MIN = 900
SESSION_BREAK_MAX = 1800
JITTER_FACTOR = 0.2

# Classifier initialization
print(f'{datetime.now()} - Loading NLP model for food categorization...')
classifier = None

def initialize_classifier():
    global classifier
    classifier = pipeline(
        "text-classification",
        model="distilbert-base-uncased-finetuned-sst-2-english",
        return_all_scores=True
    )
    print(f'{datetime.now()} - NLP model loaded successfully')

initialize_classifier()

def add_jitter(base_time):
    jitter = uniform(-JITTER_FACTOR, JITTER_FACTOR) * base_time
    return max(1, base_time + jitter)

def preprocess_text(text):
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'#(\w+)', r'\1', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_food_terms(text):
    food_terms = [
        'vegetable', 'fruit', 'meat', 'dairy', 'grain', 'protein', 'carb', 'fat',
        'sugar', 'salt', 'meal', 'breakfast', 'lunch', 'dinner', 'snack', 'diet',
        'nutrition', 'calorie', 'vitamin', 'mineral', 'fiber', 'organic', 'processed',
        'fast food', 'restaurant', 'cook', 'bake', 'fry', 'boil', 'grill', 'recipe'
    ]
    return [term for term in food_terms if term.lower() in text.lower()]

def analyze_nutrition_content(text):
    clean_text = preprocess_text(text)
    food_terms = extract_food_terms(clean_text)
    if not food_terms:
        return categorize_by_sentiment(clean_text)

    result = classifier(clean_text)
    sentiment_scores = result[0]
    positive_score = next(item['score'] for item in sentiment_scores if item['label'] == 'POSITIVE')
    negative_score = next(item['score'] for item in sentiment_scores if item['label'] == 'NEGATIVE')

    healthy_indicators = [
        'healthy', 'nutritious', 'balanced', 'fresh', 'homemade', 'organic',
        'natural', 'whole', 'protein', 'vitamin', 'nutrient', 'fiber',
        'exercise', 'workout', 'fitness', 'diet', 'portion', 'control'
    ]
    unhealthy_indicators = [
        'junk', 'fast food', 'fried', 'greasy', 'fatty', 'sugar', 'sweet',
        'processed', 'microwave', 'frozen', 'takeout', 'takeaway', 'high calorie',
        'high fat', 'high carb', 'high sugar', 'saturated', 'trans fat'
    ]

    healthy_count = sum(1 for indicator in healthy_indicators if indicator.lower() in clean_text.lower())
    unhealthy_count = sum(1 for indicator in unhealthy_indicators if indicator.lower() in clean_text.lower())

    if healthy_count > unhealthy_count:
        return "healthy" if positive_score > negative_score else "unhealthy"
    elif unhealthy_count > healthy_count:
        return "healthy" if negative_score > positive_score else "unhealthy"
    else:
        return categorize_by_sentiment(clean_text)

def categorize_by_sentiment(text):
    result = classifier(text)
    sentiment_scores = result[0]
    positive_score = next(item['score'] for item in sentiment_scores if item['label'] == 'POSITIVE')
    negative_score = next(item['score'] for item in sentiment_scores if item['label'] == 'NEGATIVE')
    return "healthy" if positive_score > negative_score else "unhealthy"

async def get_tweets(tweets, client):
    if tweets is None:
        print(f'{datetime.now()} - Starting tweet search...')
        return await client.search_tweet(QUERY, product='Top')

    wait_time = add_jitter(randint(MIN_WAIT_BETWEEN_PAGES, MAX_WAIT_BETWEEN_PAGES))
    print(f'{datetime.now()} - Waiting {wait_time:.1f}s before next page...')
    await asyncio.sleep(wait_time)
    return await tweets.next()

async def get_replies(tweet_id, client):
    try:
        return await client.search_tweet(f'conversation_id:{tweet_id}', product='Top')
    except TooManyRequests as e:
        reset_time = datetime.fromtimestamp(e.rate_limit_reset)
        wait_seconds = (reset_time - datetime.now()).total_seconds()
        print(f'{datetime.now()} - Reply rate limit hit. Waiting {wait_seconds:.1f}s...')
        await asyncio.sleep(add_jitter(wait_seconds))
        return await get_replies(tweet_id, client)

async def main():
    resume_count = 0
    if os.path.exists('tweets.csv'):
        with open('tweets.csv', 'r') as f:
            resume_count = sum(1 for _ in f) - 1

    file_mode = 'a' if resume_count > 0 else 'w'
    if file_mode == 'w':
        with open('tweets.csv', 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                'Tweet_count', 'Text', 'Retweets',
                'Likes', 'Replies', 'Image URL', 'Category'
            ])
        with open('replies.csv', 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                'Original_Text', 'Category',
                'Reply_Text', 'Likes', 'Reposts'
            ])

    config = ConfigParser()
    config.read('config.ini')
    client = Client(language='en-US')
    await client.login(
        auth_info_1=config['X']['username'],
        auth_info_2=config['X']['email'],
        password=config['X']['password']
    )

    tweet_count = resume_count
    tweets = None
    session_count = 0

    while tweet_count < MINIMUM_TWEETS:
        try:
            if session_count >= MAX_TWEETS_PER_SESSION:
                break_duration = add_jitter(randint(SESSION_BREAK_MIN, SESSION_BREAK_MAX))
                print(f'{datetime.now()} - Session limit reached. Sleeping {break_duration/60:.1f}min...')
                await asyncio.sleep(break_duration)
                session_count = 0

            tweets = await get_tweets(tweets, client)
            if not tweets:
                print(f'{datetime.now()} - No more tweets found')
                break

            for tweet in tweets:
                if REPLY_THRESHOLD <= tweet.reply_count <= 8:
                    tweet_count += 1
                    session_count += 1

                    # Process tweet
                    image_url = next((m.media_url for m in tweet.media if m.type == 'photo'), 'N/A')
                    category = analyze_nutrition_content(tweet.text)

                    # Write tweet data
                    with open('tweets.csv', 'a', newline='', encoding='utf-8') as f:
                        csv.writer(f).writerow([
                            tweet_count, tweet.text,
                            tweet.retweet_count, tweet.favorite_count,
                            tweet.reply_count, image_url, category
                        ])

                    # Process replies
                    replies = await get_replies(tweet.id, client)
                    for reply in replies:
                        if reply.id != tweet.id:
                            with open('replies.csv', 'a', newline='', encoding='utf-8') as f:
                                csv.writer(f).writerow([
                                    tweet.text, category,
                                    reply.text, reply.favorite_count,
                                    reply.retweet_count
                                ])

                    # Rate limiting
                    wait_time = add_jitter(randint(MIN_WAIT_BETWEEN_TWEETS, MAX_WAIT_BETWEEN_TWEETS))
                    print(f'{datetime.now()} - Waiting {wait_time:.1f}s...')
                    await asyncio.sleep(wait_time)

            print(f'{datetime.now()} - Progress: {tweet_count}/{MINIMUM_TWEETS} tweets')

        except Exception as e:
            print(f'{datetime.now()} - Error: {str(e)}')
            await asyncio.sleep(add_jitter(60))

    print(f'{datetime.now()} - Completed! Total collected: {tweet_count}')

if __name__ == '__main__':
    asyncio.run(main())
