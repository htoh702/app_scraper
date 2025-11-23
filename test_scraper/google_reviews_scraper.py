from google_play_scraper import reviews, Sort
import pandas as pd
from datetime import datetime, timedelta

result, continuation_token = reviews(
    'kr.co.kbc.cha.android',
    lang='ko',
    country='kr', 
    sort=Sort.NEWEST,
    count=200 
)

total_reviews = []

total_reviews.extend(result)

today = datetime.now().date()
target_date = today - timedelta(days=30)
print(target_date)

target_date = pd.to_datetime(target_date, format="%Y-%m")

df = pd.DataFrame(total_reviews)

df["at"] = pd.to_datetime(df["at"])
# df = df[df["at"].dt.date == pd.to_datetime(target_date).date()]
df = df[(df["at"].dt.year == target_date.year) & (df["at"].dt.month == target_date.month)]
print(df)


df.to_csv("kb_chachacha_google_reviews.csv", index=False, encoding="utf-8-sig")