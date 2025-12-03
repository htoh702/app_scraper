import pandas as pd

def preprocess_reviews(csv_path):
    # CSV 로드
    df = pd.read_csv(csv_path)

    # date를 datetime으로 변환
    df['date'] = pd.to_datetime(df['date'], errors='coerce')

    # 2025년 데이터만 필터링
    df_2025 = df[df['date'].dt.year == 2025].copy()

    # 월 컬럼 생성 (2025-01, 2025-02 ...)
    df_2025['month'] = df_2025['date'].dt.to_period('M').astype(str)

    # ------------------------------------
    # 1) 월별 총 리뷰 개수
    # ------------------------------------
    monthly_count = df_2025.groupby('month').size().reset_index(name='review_count')

    return monthly_count


# 사용 예시
csv_file = "./kbchachacha_reviews_20251203_225010.csv"

monthly_count = preprocess_reviews(csv_file)

print("=== 월별 총 리뷰 개수 ===")
print(monthly_count)


###########################
# === 월별 총 리뷰 개수 ===
#       month  review_count
# 0   2025-01            14
# 1   2025-02            69
# 2   2025-03            11
# 3   2025-04           156
# 4   2025-05            11
# 5   2025-06           111
# 6   2025-07             6
# 7   2025-08            67
# 8   2025-09            10
# 9   2025-10             8
# 10  2025-11             8
