from twikit import Client, TooManyRequests
import time
import asyncio
from datetime import datetime
import csv
from configparser import ConfigParser
from random import randint
from transformers import pipeline

# Load a zero-shot classification model
classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

def classify_tweet(text):
    categories = ["healthy lifestyle", "unhealthy lifestyle"]
    result = classifier(text, candidate_labels=categories)
    return result["labels"][0]  # Returns "healthy lifestyle" or "unhealthy lifestyle"


# Constants
MINIMUM_TWEETS = 100
QUERY = '("#food" OR "#diet" OR "#nutrition") lang:en -filter:retweets since:2020-01-01 until:2025-12-31'
RETWEET_THRESHOLD = 2
LIKE_THRESHOLD = 10
REPLY_THRESHOLD = 5  # Set the reply threshold to filter tweets with fewer replies


async def get_tweets(tweets, client):
    if tweets is None:
        print(f'{datetime.now()} - Fetching tweets...')
        tweets = await client.search_tweet(QUERY, product='Top')
    else:
        wait_time = randint(5, 20)
        print(f'{datetime.now()} - Fetching next tweets after {wait_time} seconds...')
        await asyncio.sleep(wait_time)
        tweets = await tweets.next()

    return tweets


async def get_replies(tweet_id, client):
    # This function gets replies for a specific tweet
    replies = await client.search_tweet(f'conversation_id:{tweet_id}', product='Top')
    return replies


async def main():
    # Load credentials
    config = ConfigParser()
    config.read('config.ini')
    username = config['X']['username']
    email = config['X']['email']
    password = config['X']['password']

    # Create CSV files
    with open('tweets.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Tweet_count', 'Username', 'Text', 'Created At', 'Retweets', 'Likes', 'Hashtags', 'Image URL', 'Category'])

    with open('replies.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Tweet Text', 'Category', 'Reply Text', 'Reply Likes', 'Reply Reposts'])

    # Authenticate
    client = Client(language='en-US')
    await client.login(auth_info_1=username, auth_info_2=email, password=password)
    client.save_cookies('cookies.json')

    tweet_count = 0
    tweets = None

    while tweet_count < MINIMUM_TWEETS:
        try:
            tweets = await get_tweets(tweets, client)
        except TooManyRequests as e:
            rate_limit_reset = datetime.fromtimestamp(e.rate_limit_reset)
            print(f'{datetime.now()} - Rate limit hit. Waiting until {rate_limit_reset}')
            wait_time = (rate_limit_reset - datetime.now()).total_seconds()
            await asyncio.sleep(wait_time)
            continue

        if not tweets:
            print(f'{datetime.now()} - No more tweets found')
            break

        for tweet in tweets:
            # Apply popularity filter
            if tweet.retweet_count >= RETWEET_THRESHOLD or tweet.favorite_count >= LIKE_THRESHOLD or tweet.reply_count >= REPLY_THRESHOLD:
                tweet_count += 1

                # Extract hashtags
                hashtags = tweet.hashtags if tweet.hashtags else []

                # Extract image URL
                image_url = None
                if tweet.media:
                    for media in tweet.media:
                        if media.type == 'photo':
                            image_url = media.media_url

                # Categorize tweet
                category = classify_tweet(tweet.text)

                # Get reply count (assuming tweet.reply_count exists)
                reply_count = tweet.reply_count if hasattr(tweet, 'reply_count') else 0

                # Save tweet data
                tweet_data = [
                    tweet_count, tweet.user.name, tweet.text, tweet.created_at, tweet.retweet_count,
                    tweet.favorite_count, ', '.join(hashtags), image_url if image_url else 'N/A', category
                ]

                with open('tweets.csv', 'a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(tweet_data)

                # Get replies for the tweet
                replies = await get_replies(tweet.id, client)

                for reply in replies:
                    reply_text = reply.text
                    reply_likes = reply.favorite_count
                    reply_reposts = reply.retweet_count

                    # Save reply data to the new CSV file
                    reply_data = [
                        tweet.text, category, reply_text, reply_likes, reply_reposts
                    ]

                    with open('replies.csv', 'a', newline='') as file:
                        writer = csv.writer(file)
                        writer.writerow(reply_data)

        print(f'{datetime.now()} - Collected {tweet_count} tweets')

    print(f'{datetime.now()} - Done! Total tweets collected: {tweet_count}')


# Run the script
if __name__ == '__main__':
    asyncio.run(main())
