import requests
import pandas as pd
import time
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional, Union
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    from google_play_scraper import reviews, Sort
    GOOGLE_PLAY_AVAILABLE = True
except ImportError:
    GOOGLE_PLAY_AVAILABLE = False
    print("⚠️  google-play-scraper가 설치되지 않았습니다. Google Play 리뷰 수집이 비활성화됩니다.")
    print("   설치하려면: pip install google-play-scraper")


class UnifiedReviewMonitor:
    def __init__(self, ios_app_id: str = None, android_package_name: str = None,
                 country: str = "kr", lang: str = "ko", check_interval: int = 300):
        """
        iOS와 Android 리뷰를 통합 모니터링하는 클래스
        
        Args:
            ios_app_id: iOS App Store 앱 ID
            android_package_name: Android 패키지명
            country: 국가 코드 (기본값: kr)
            lang: 언어 코드 (기본값: ko)
            check_interval: 체크 간격(초, 기본값: 5분)
        """
        self.ios_app_id = ios_app_id
        self.android_package_name = android_package_name
        self.country = country
        self.lang = lang
        self.check_interval = check_interval
        
        # 플랫폼별 설정
        self.ios_enabled = bool(ios_app_id)
        self.android_enabled = bool(android_package_name and GOOGLE_PLAY_AVAILABLE)
        
        if not self.ios_enabled and not self.android_enabled:
            raise ValueError("iOS 앱 ID 또는 Android 패키지명 중 하나는 반드시 제공해야 합니다.")
        
        # 데이터 저장 구조
        self.seen_reviews = {
            'ios': set(),
            'android': set()
        }
        
        self.data_dir = Path("unified_review_data")
        self.data_dir.mkdir(exist_ok=True)
        
        # 기존 리뷰 ID 로드
        self._load_seen_reviews()
    
    def _load_seen_reviews(self) -> None:
        """기존에 확인한 리뷰 ID들을 로드합니다."""
        for platform in ['ios', 'android']:
            seen_file = self.data_dir / f"seen_{platform}_reviews.json"
            if seen_file.exists():
                try:
                    with open(seen_file, 'r', encoding='utf-8') as f:
                        self.seen_reviews[platform] = set(json.load(f))
                    print(f"{platform.upper()} 기존 리뷰 {len(self.seen_reviews[platform])}개를 로드했습니다.")
                except Exception as e:
                    print(f"{platform.upper()} 기존 리뷰 로드 실패: {e}")
    
    def _save_seen_reviews(self) -> None:
        """확인한 리뷰 ID들을 저장합니다."""
        for platform in ['ios', 'android']:
            seen_file = self.data_dir / f"seen_{platform}_reviews.json"
            try:
                with open(seen_file, 'w', encoding='utf-8') as f:
                    json.dump(list(self.seen_reviews[platform]), f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"{platform.upper()} 리뷰 ID 저장 실패: {e}")
    
    def _create_ios_review_id(self, review: Dict) -> str:
        """iOS 리뷰의 고유 ID를 생성합니다."""
        content = f"{review['author']}_{review['title']}_{review['content']}_{review['updated']}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _create_android_review_id(self, review: Dict) -> str:
        """Android 리뷰의 고유 ID를 생성합니다."""
        if 'reviewId' in review and review['reviewId']:
            return review['reviewId']
        content = f"{review['userName']}_{review.get('content', '')}_{review['at']}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def fetch_ios_reviews(self) -> List[Dict]:
        """iOS App Store에서 리뷰를 가져옵니다."""
        if not self.ios_enabled:
            return []
        
        url = f"https://itunes.apple.com/{self.country}/rss/customerreviews/id={self.ios_app_id}/sortBy=mostRecent/json"
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            entries = data["feed"]["entry"]
            
            reviews = []
            for entry in entries:
                try:
                    review = {
                        "platform": "iOS",
                        "author": entry['author']['name']['label'],
                        "rating": int(entry['im:rating']['label']),
                        "title": entry['title']['label'],
                        "content": entry['content']['label'],
                        "updated": entry['updated']['label'],
                        "app_id": self.ios_app_id
                    }
                    reviews.append(review)
                except KeyError:
                    continue
            
            return reviews
            
        except Exception as e:
            print(f"[iOS] API 요청 실패: {e}")
            return []
    
    def fetch_android_reviews(self) -> List[Dict]:
        """Google Play Store에서 리뷰를 가져옵니다."""
        if not self.android_enabled:
            return []
        
        try:
            result, continuation_token = reviews(
                self.android_package_name,
                lang=self.lang,
                country=self.country,
                sort=Sort.NEWEST,
                count=200
            )
            
            google_reviews = []
            for review in result:
                # 불필요한 필드 제거하고 플랫폼 정보 추가
                cleaned_review = {k: v for k, v in review.items() 
                                if k not in ['userImage', 'reviewCreatedVersion']}
                cleaned_review["platform"] = "Android"
                cleaned_review["package_name"] = self.android_package_name
                
                # iOS와 필드명 통일
                cleaned_review["rating"] = cleaned_review.get("score", 0)
                cleaned_review["author"] = cleaned_review.get("userName", "")
                cleaned_review["updated"] = cleaned_review.get("at", "")
                
                google_reviews.append(cleaned_review)
            
            return google_reviews
            
        except Exception as e:
            print(f"[Android] 리뷰 가져오기 실패: {e}")
            return []
    
    def fetch_all_reviews(self) -> Dict[str, List[Dict]]:
        """모든 플랫폼의 리뷰를 병렬로 가져옵니다."""
        results = {"ios": [], "android": []}
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            
            if self.ios_enabled:
                futures['ios'] = executor.submit(self.fetch_ios_reviews)
            
            if self.android_enabled:
                futures['android'] = executor.submit(self.fetch_android_reviews)
            
            for platform, future in futures.items():
                try:
                    results[platform] = future.result(timeout=60)
                except Exception as e:
                    print(f"[{platform.upper()}] 리뷰 수집 실패: {e}")
                    results[platform] = []
        
        return results
    
    def filter_new_reviews(self, all_reviews: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
        """새로운 리뷰만 필터링합니다."""
        new_reviews = {"ios": [], "android": []}
        
        # iOS 리뷰 필터링
        for review in all_reviews["ios"]:
            review_id = self._create_ios_review_id(review)
            if review_id not in self.seen_reviews["ios"]:
                new_reviews["ios"].append(review)
                self.seen_reviews["ios"].add(review_id)
        
        # Android 리뷰 필터링
        for review in all_reviews["android"]:
            review_id = self._create_android_review_id(review)
            if review_id not in self.seen_reviews["android"]:
                new_reviews["android"].append(review)
                self.seen_reviews["android"].add(review_id)
        
        return new_reviews
    
    def save_new_reviews(self, new_reviews: Dict[str, List[Dict]]) -> None:
        """새로운 리뷰를 플랫폼별로 저장합니다."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for platform, reviews in new_reviews.items():
            if reviews:
                df = pd.DataFrame(reviews)
                if platform == "ios":
                    df["updated"] = pd.to_datetime(df["updated"])
                else:  # android
                    df["at"] = pd.to_datetime(df["at"])
                
                filename = self.data_dir / f"new_{platform}_reviews_{timestamp}.csv"
                df.to_csv(filename, index=False, encoding="utf-8-sig")
                print(f"[{platform.upper()}] 새로운 리뷰 {len(reviews)}개가 '{filename}'에 저장되었습니다.")
    
    def save_unified_reviews(self, new_reviews: Dict[str, List[Dict]]) -> None:
        """모든 플랫폼의 새 리뷰를 하나의 파일로 통합 저장합니다."""
        all_new_reviews = []
        
        # iOS 리뷰 표준화
        for review in new_reviews["ios"]:
            unified_review = {
                "platform": "iOS",
                "author": review["author"],
                "rating": review["rating"],
                "title": review.get("title", ""),
                "content": review["content"],
                "date": pd.to_datetime(review["updated"]).strftime('%Y-%m-%d %H:%M:%S'),
                "thumbs_up": None,
                "developer_reply": None,
                "app_identifier": review["app_id"]
            }
            all_new_reviews.append(unified_review)
        
        # Android 리뷰 표준화
        for review in new_reviews["android"]:
            unified_review = {
                "platform": "Android",
                "author": review["userName"],
                "rating": review["score"],
                "title": None,
                "content": review.get("content", ""),
                "date": pd.to_datetime(review["at"]).strftime('%Y-%m-%d %H:%M:%S'),
                "thumbs_up": review.get("thumbsUpCount", 0),
                "developer_reply": review.get("replyContent", None),
                "app_identifier": review["package_name"],
                "ap_version": review.get("appVersion", "")
            }
            all_new_reviews.append(unified_review)
        
        if all_new_reviews:
            df = pd.DataFrame(all_new_reviews)
            df = df.sort_values("date", ascending=False)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.data_dir / f"unified_new_reviews_{timestamp}.csv"
            df.to_csv(filename, index=False, encoding="utf-8-sig")
            print(f"[통합] 새로운 리뷰 {len(all_new_reviews)}개가 '{filename}'에 저장되었습니다.")
    
    def display_new_reviews(self, new_reviews: Dict[str, List[Dict]]) -> None:
        """새로운 리뷰를 플랫폼별로 화면에 출력합니다."""
        total_new = sum(len(reviews) for reviews in new_reviews.values())
        
        if total_new == 0:
            return
        
        print(f"\n{'='*80}")
        print(f"🆕 새로운 리뷰 총 {total_new}개 발견!")
        print(f"   📱 iOS: {len(new_reviews['ios'])}개")
        print(f"   🤖 Android: {len(new_reviews['android'])}개")
        print(f"{'='*80}")
        
        # iOS 리뷰 출력
        if new_reviews["ios"]:
            print(f"\n📱 iOS App Store 리뷰 ({len(new_reviews['ios'])}개)")
            print("-" * 60)
            for i, review in enumerate(new_reviews["ios"], 1):
                print(f"리뷰 #{i}")
                print(f"⭐ 평점: {'★' * review['rating']}{'☆' * (5 - review['rating'])} ({review['rating']}/5)")
                print(f"👤 작성자: {review['author']}")
                print(f"📅 작성일: {pd.to_datetime(review['updated']).strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"📝 제목: {review['title']}")
                content = review['content'][:200] + ("..." if len(review['content']) > 200 else "")
                print(f"💬 내용: {content}")
                print()
        
        # Android 리뷰 출력
        if new_reviews["android"]:
            print(f"\n🤖 Google Play 리뷰 ({len(new_reviews['android'])}개)")
            print("-" * 60)
            for i, review in enumerate(new_reviews["android"], 1):
                print(f"리뷰 #{i}")
                print(f"⭐ 평점: {'★' * review['score']}{'☆' * (5 - review['score'])} ({review['score']}/5)")
                print(f"👤 작성자: {review['userName']}")
                print(f"📅 작성일: {pd.to_datetime(review['at']).strftime('%Y-%m-%d %H:%M:%S')}")
                content = review.get('content', '내용 없음')[:200]
                content += "..." if len(review.get('content', '')) > 200 else ""
                print(f"💬 내용: {content}")
                if review.get('thumbsUpCount', 0) > 0:
                    print(f"👍 좋아요: {review['thumbsUpCount']}")
                if review.get('replyContent'):
                    reply_content = review['replyContent'][:100] + "..."
                    print(f"🏢 개발자 답변: {reply_content}")
                print()
    
    def get_unified_stats(self, new_reviews: Dict[str, List[Dict]]) -> Dict:
        """통합 리뷰 통계를 계산합니다."""
        stats = {
            "total_count": 0,
            "ios_count": len(new_reviews["ios"]),
            "android_count": len(new_reviews["android"]),
            "avg_rating": 0,
            "platform_ratings": {},
            "latest_review_time": None
        }
        
        all_ratings = []
        all_times = []
        
        # iOS 통계
        if new_reviews["ios"]:
            ios_ratings = [r["rating"] for r in new_reviews["ios"]]
            ios_times = [pd.to_datetime(r["updated"], utc=True) for r in new_reviews["ios"]]
            stats["platform_ratings"]["iOS"] = sum(ios_ratings) / len(ios_ratings)
            all_ratings.extend(ios_ratings)
            all_times.extend(ios_times)
        
        # Android 통계
        if new_reviews["android"]:
            android_ratings = [r["score"] for r in new_reviews["android"]]
            android_times = [pd.to_datetime(r["at"], utc=True) for r in new_reviews["android"]]
            stats["platform_ratings"]["Android"] = sum(android_ratings) / len(android_ratings)
            all_ratings.extend(android_ratings)
            all_times.extend(android_times)
        
        if all_ratings:
            stats["total_count"] = len(all_ratings)
            stats["avg_rating"] = sum(all_ratings) / len(all_ratings)
            stats["latest_review_time"] = max(all_times).strftime('%Y-%m-%d %H:%M:%S')
        
        return stats
    
    def send_notification(self, new_reviews: Dict[str, List[Dict]]) -> None:
        """새 리뷰 통합 알림을 보냅니다."""
        stats = self.get_unified_stats(new_reviews)
        
        if stats["total_count"] > 0:
            print(f"\n🔔 통합 알림:")
            print(f"   📊 총 새 리뷰: {stats['total_count']}개")
            print(f"   📱 iOS: {stats['ios_count']}개")
            print(f"   🤖 Android: {stats['android_count']}개")
            print(f"   ⭐ 전체 평균 평점: {stats['avg_rating']:.1f}/5.0")
            
            for platform, rating in stats["platform_ratings"].items():
                print(f"   {platform} 평균: {rating:.1f}/5.0")
            
            print(f"   🕐 최근 리뷰: {stats['latest_review_time']}")
    
    def start_monitoring(self, duration_hours: Optional[int] = None, 
                        save_unified: bool = True) -> None:
        """통합 리뷰 모니터링을 시작합니다."""
        print(f"🚀 통합 앱 리뷰 모니터링 시작!")
        
        if self.ios_enabled:
            print(f"📱 iOS App ID: {self.ios_app_id}")
        if self.android_enabled:
            print(f"🤖 Android Package: {self.android_package_name}")
        
        print(f"📊 체크 간격: {self.check_interval}초")
        if duration_hours:
            print(f"⏰ 실행 시간: {duration_hours}시간")
        print("🛑 중지하려면 Ctrl+C를 눌러주세요.\n")
        
        start_time = datetime.now()
        check_count = 0
        
        try:
            while True:
                check_count += 1
                current_time = datetime.now()
                elapsed_hours = (current_time - start_time).total_seconds() / 3600
                
                if duration_hours and elapsed_hours >= duration_hours:
                    print(f"\n⏰ 설정된 {duration_hours}시간이 경과하여 모니터링을 종료합니다.")
                    break
                
                print(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] 체크 #{check_count}")
                print("📥 모든 플랫폼 리뷰 확인 중...")
                
                # 모든 플랫폼 리뷰 수집
                all_reviews = self.fetch_all_reviews()
                new_reviews = self.filter_new_reviews(all_reviews)
                
                total_new = sum(len(reviews) for reviews in new_reviews.values())
                
                if total_new > 0:
                    self.display_new_reviews(new_reviews)
                    self.save_new_reviews(new_reviews)
                    if save_unified:
                        self.save_unified_reviews(new_reviews)
                    self.send_notification(new_reviews)
                    self._save_seen_reviews()
                else:
                    print("새로운 리뷰가 없습니다.")
                
                print(f"⏳ {self.check_interval}초 후 다시 확인합니다...\n")
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 사용자에 의해 모니터링이 중단되었습니다.")
            print(f"📈 총 {check_count}회 체크했습니다.")
            print(f"⏰ 총 실행시간: {(datetime.now() - start_time).total_seconds() / 3600:.1f}시간")


def one_time_unified_fetch(ios_app_id: str = None, android_package_name: str = None,
                          target_date: str = None, country: str = "kr"):
    """통합 일회성 리뷰 수집"""
    print("📱 통합 리뷰 수집을 시작합니다...")
    
    monitor = UnifiedReviewMonitor(ios_app_id, android_package_name, country)
    all_reviews = monitor.fetch_all_reviews()
    
    # 날짜 필터링 (옵션)
    if target_date:
        # TODO: 날짜 필터링 로직 추가
        pass
    
    print(f"📊 수집 결과:")
    print(f"   📱 iOS: {len(all_reviews['ios'])}개")
    print(f"   🤖 Android: {len(all_reviews['android'])}개")
    
    # 통합 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 플랫폼별 저장
    for platform, reviews in all_reviews.items():
        if reviews:
            df = pd.DataFrame(reviews)
            filename = f"unified_{platform}_reviews_{timestamp}.csv"
            df.to_csv(filename, index=False, encoding="utf-8-sig")
            print(f"[{platform.upper()}] 리뷰가 '{filename}'에 저장되었습니다.")


def main():
    """메인 실행 함수"""
    print("📱 통합 앱 리뷰 모니터링 시스템")
    print("=" * 50)
    
    # 앱 설정
    IOS_APP_ID = "1112366886"  # KB차차차 iOS
    ANDROID_PACKAGE_NAME = "kr.co.kbc.cha.android"  # KB차차차 Android
    
    # 모니터링 설정
    CHECK_INTERVAL = 300  # 5분
    DURATION_HOURS = None  # 무한 실행
    SAVE_UNIFIED = True   # 통합 파일 저장 여부
    
    print("1. 실시간 통합 모니터링")
    print("2. 일회성 통합 수집")
    print("3. iOS만 모니터링")
    print("4. Android만 모니터링")
    
    choice = input("선택하세요 (1-4): ").strip()
    
    if choice == "1":
        # 통합 실시간 모니터링
        monitor = UnifiedReviewMonitor(
            ios_app_id=IOS_APP_ID,
            android_package_name=ANDROID_PACKAGE_NAME,
            check_interval=CHECK_INTERVAL
        )
        monitor.start_monitoring(DURATION_HOURS, SAVE_UNIFIED)
        
    elif choice == "2":
        # 통합 일회성 수집
        one_time_unified_fetch(IOS_APP_ID, ANDROID_PACKAGE_NAME)
        
    elif choice == "3":
        # iOS만 모니터링
        monitor = UnifiedReviewMonitor(
            ios_app_id=IOS_APP_ID,
            check_interval=CHECK_INTERVAL
        )
        monitor.start_monitoring(DURATION_HOURS)
        
    elif choice == "4":
        # Android만 모니터링
        if not GOOGLE_PLAY_AVAILABLE:
            print("❌ google-play-scraper 라이브러리가 필요합니다.")
            return
        monitor = UnifiedReviewMonitor(
            android_package_name=ANDROID_PACKAGE_NAME,
            check_interval=CHECK_INTERVAL
        )
        monitor.start_monitoring(DURATION_HOURS)
        
    else:
        print("잘못된 선택입니다.")


if __name__ == "__main__":
    main()
