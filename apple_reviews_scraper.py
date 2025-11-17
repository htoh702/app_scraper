import requests
import pandas as pd
import json
from datetime import datetime, timedelta

# 23.46.236.31 443

app_id = "1112366886"
url = f"https://itunes.apple.com/kr/rss/customerreviews/id={app_id}/sortBy=mostRecent/json"

response = requests.get(url).json()
entries = response["feed"]["entry"]
data = []
for r in entries:
    data.append({
        "author": r['author']['name']['label'],
        "rating": r['im:rating']['label'],
        "title": r['title']['label'],
        "content": r['content']['label'],
        "updated": r['updated']['label'],
    })

df = pd.DataFrame(data)

today = datetime.now().date()
# target_date = today - timedelta(days=7)
# print(target_date)

target_date = '2025-03'
target_date = pd.to_datetime(target_date, format="%Y-%m")

df["updated"] = pd.to_datetime(df["updated"])
# df = df[df["updated"].dt.date == pd.to_datetime(target_date).date()]
df = df[(df["updated"].dt.year == target_date.year) & (df["updated"].dt.month == target_date.month)]

print(df)

df.to_csv("kb_chachacha_ios_reviews.csv", index=False, encoding="utf-8-sig")
