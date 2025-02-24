from twikit import Client, TooManyRequests
import time
from datetime import datetime
import csv
from configparser import ConfigParser
from random import randint
import asyncio  # Import asyncio for asynchronous programming

MINIMUM_TWEETS = 100
# Modifier la QUERY pour pondérer les termes
QUERY = '   ("alimentation saine" OR "hydratation" OR "régime équilibré" OR "alimentation" OR "nutrition" OR "healthy" )  lang:fr -filter:retweets  since:2020-01-01 until:2025-12-31'

# Rééquilibrer les mots-clés santé
HEALTHY_KEYWORDS = [   'healthy', 'alimentation saine', 'nutrition', 'régime équilibré',    'bien-être', 'healthy food', 'superfoods', 'superaliments',   'antioxydants', 'remèdes naturels', 'vitamines', 'sport',    'activité physique', 'santé intestinale', 'balanced diet',    'boire de l\'eau', 'manger équilibré']

UNHEALTHY_KEYWORDS = [    'fast food', 'malbouffe', 'soda', 'cigarette', 'tabac', 'clope',   'obésité', 'fumer', 'boisson sucrée', 'excès alimentaire',    'manger tard', 'narguilé', 'chicha', 'addiction', 'grignotage',   'sédentarité']
# Define a threshold for popularity (for example, at least 100 retweets or likes)
RETWEET_THRESHOLD = 2
LIKE_THRESHOLD = 10


async def get_tweets(tweets, client):
    if tweets is None:
        print(f'{datetime.now()} - Getting tweets...')
        tweets = await client.search_tweet(QUERY, product='Top')  # Await the coroutine
    else:
        wait_time = randint(5, 20)
        print(f'{datetime.now()} - Getting next tweets after {wait_time} seconds ...')
        time.sleep(wait_time)
        tweets = await tweets.next()  # Await the coroutine

    return tweets


async def main():
    #* login credentials
    config = ConfigParser()
    config.read('config.ini')
    username = config['X']['username']
    email = config['X']['email']
    password = config['X']['password']

    #* create a csv file
    with open('tweets.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Tweet_count', 'Username', 'Text', 'Created At', 'Retweets', 'Likes', 'Hashtags', 'Image URL', 'Category'])

    #* authenticate to X.com
    client = Client(language='en-US')
    await client.login(auth_info_1=username, auth_info_2=email, password=password)  # Await the coroutine
    client.save_cookies('cookies.json')  # Await the coroutine

    # client.load_cookies('cookies.json')  # Uncomment this if you already have cookies

    tweet_count = 0
    tweets = None

    while tweet_count < MINIMUM_TWEETS:
        try:
            tweets = await get_tweets(tweets, client)  # Await the coroutine
        except TooManyRequests as e:
            rate_limit_reset = datetime.fromtimestamp(e.rate_limit_reset)
            print(f'{datetime.now()} - Rate limit reached. Waiting until {rate_limit_reset}')
            wait_time = rate_limit_reset - datetime.now()
            time.sleep(wait_time.total_seconds())
            continue

        if not tweets:
            print(f'{datetime.now()} - No more tweets found')
            break

        for tweet in tweets:
            # Filter popular tweets based on retweets and likes
            if tweet.retweet_count >= RETWEET_THRESHOLD or tweet.favorite_count >= LIKE_THRESHOLD:
                tweet_count += 1

                # Extract hashtags (directly using the strings from tweet.hashtags)
                hashtags = tweet.hashtags  # tweet.hashtags is now a list of strings

                # Extract image URL if available
                image_url = None
                if tweet.media:
                    for media in tweet.media:
                        print(f'Media found: {media}')  # Debugging output to inspect the media object
                        if media.type == 'photo':  # Assuming image URLs are under 'photo' type
                            image_url = media.media_url  # Adjust this to the correct attribute if necessary

                # Categorize the tweet
                tweet_text = tweet.text.lower()
                category = 'mix'  # Default to 'mix'

                if any(keyword in tweet_text for keyword in HEALTHY_KEYWORDS):
                    if any(keyword in tweet_text for keyword in UNHEALTHY_KEYWORDS):
                        category = 'mix'
                    else:
                        category = 'healthy'
                elif any(keyword in tweet_text for keyword in UNHEALTHY_KEYWORDS):
                    category = 'unhealthy'

                tweet_data = [
                    tweet_count, tweet.user.name, tweet.text, tweet.created_at, tweet.retweet_count,
                    tweet.favorite_count, ', '.join(hashtags), image_url if image_url else 'N/A', category
                ]

                # Write tweet data to CSV
                with open('tweets.csv', 'a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(tweet_data)

        print(f'{datetime.now()} - Got {tweet_count} tweets')

    print(f'{datetime.now()} - Done! Got {tweet_count} tweets found')


# Run the async main function
if __name__ == '__main__':
    asyncio.run(main())
