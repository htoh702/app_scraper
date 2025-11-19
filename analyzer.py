import pandas as pd
import glob
import re
import os

# 분석할 파일 경로
file_paths = glob.glob("./unified_review_data/*_reviews_*.csv")

# 앱 이름 패턴
apps = ["kbchachacha", "heydealer", "encar"]

# 앱별 데이터 저장 dict
app_data = {app: [] for app in apps}

# 파일을 앱 이름별로 그룹핑
for file in file_paths:
    for app in apps:
        if app in file:
            app_data[app].append(file)

def analyze_app(app_name, file_list):
    # 파일 통합 로드
    df_list = [pd.read_csv(f) for f in file_list]
    df = pd.concat(df_list, ignore_index=True)

    # 저장용 데이터프레임 리스트
    export_sections = []

    # 1. 플랫폼별 리뷰 수
    platform_stats = df["platform"].value_counts(dropna=False).reset_index()
    platform_stats.columns = ["platform", "review_count"]
    export_sections.append(("platform_review_count", platform_stats))

    # 2. 평점별 분포
    rating_stats = df["rating"].value_counts().sort_index().reset_index()
    rating_stats.columns = ["rating", "count"]
    export_sections.append(("rating_distribution", rating_stats))

    # 3. 좋아요 TOP 5
    top5 = df.nlargest(5, "thumbs_up")[["thumbs_up", "author", "content"]]
    export_sections.append(("top5_likes", top5))

    # 4. 버전별 평균 평점 + 리뷰 개수 TOP 5
    version_stats = (
        df.groupby("ap_version")["rating"]
        .agg(["mean", "count"])
        .sort_values("count", ascending=False)
        .head(5)
        .reset_index()
    )
    export_sections.append(("version_rating_top5", version_stats))

    # CSV 저장
    os.makedirs("./analysis", exist_ok=True)
    output_path = f"./analysis/{app_name}_analysis.csv"

    # 한 파일에 여러 섹션을 이어붙여 저장
    with open(output_path, "w", encoding="utf-8-sig") as f:
        for title, section_df in export_sections:
            f.write(f"### {title}\n")
            section_df.to_csv(f, index=False)
            f.write("\n\n")


# 앱별 분석 실행
for app, files in app_data.items():
    if files:
        analyze_app(app, files)
