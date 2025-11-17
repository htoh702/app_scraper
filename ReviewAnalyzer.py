import os
import glob
import pandas as pd
from datetime import datetime, timedelta
import requests
import json
from pathlib import Path

class ReviewAnalyzer:
    def __init__(self, data_dir="./unified_review_data", ollama_url="http://localhost:11434"):
        self.data_dir = data_dir
        self.ollama_url = ollama_url
        self.our_app_files = []  # 우리 회사 앱
        self.competitor_files = []  # 경쟁사 앱
        
    def get_last_month_files(self):
        """전달 데이터 파일 수집"""
        
        # 전달의 모든 날짜 패턴 생성
        all_files = glob.glob(os.path.join(self.data_dir, "*.csv"))
        
        for file in all_files:
            filename = os.path.basename(file)
            try:
                # 파일명에서 날짜 추출
                # unified_new_reviews_20241117_132841.csv
                # heydealer_reviews_20241117_132841.csv
                parts = filename.split('_')
                
                # timestamp 위치 찾기 (yyyymmdd 형식)
                date_str = None
                for part in parts:
                    if len(part) == 8 and part.isdigit():
                        date_str = part
                        break
                
                if not date_str:
                    continue
                
                file_date = datetime.strptime(date_str, "%Y%m%d")
                
                # 전달 데이터인지 확인
                if filename.startswith("kbchachacha_reviews_"):
                    self.our_app_files.append(file)
                elif filename.startswith("heydealer_reviews_"):
                    self.competitor_files.append(file)
            except (IndexError, ValueError) as e:
                print(f"파일명 형식 오류: {filename} - {e}")
                continue
        
        print(f"수집된 우리 회사 앱 파일: {len(self.our_app_files)}개")
        print(f"수집된 경쟁사 앱 파일: {len(self.competitor_files)}개")
        
    def load_and_merge_data(self):
        """데이터 로드 및 병합"""
        our_app_df = pd.DataFrame()
        competitor_df = pd.DataFrame()
        
        # 우리 회사 앱 데이터 병합
        if self.our_app_files:
            our_app_dfs = []
            for file in self.our_app_files:
                try:
                    df = pd.read_csv(file)
                    our_app_dfs.append(df)
                except Exception as e:
                    print(f"우리 앱 파일 로드 실패 ({file}): {e}")
            
            if our_app_dfs:
                our_app_df = pd.concat(our_app_dfs, ignore_index=True)
                # 중복 제거: platform, author, content, updated 조합으로
                our_app_df.drop_duplicates(
                    subset=['platform', 'author', 'content', 'date', 'ap_version'], 
                    keep='first', 
                    inplace=True
                )
        
        # 경쟁사 앱 데이터 병합
        if self.competitor_files:
            competitor_dfs = []
            for file in self.competitor_files:
                try:
                    df = pd.read_csv(file)
                    competitor_dfs.append(df)
                except Exception as e:
                    print(f"경쟁사 파일 로드 실패 ({file}): {e}")
            
            if competitor_dfs:
                competitor_df = pd.concat(competitor_dfs, ignore_index=True)
                # 중복 제거
                competitor_df.drop_duplicates(
                    subset=['platform', 'author', 'content', 'date', 'ap_version'], 
                    keep='first', 
                    inplace=True
                )
        
        print(f"\n로드된 우리 회사 앱 리뷰: {len(our_app_df)}건")
        print(f"로드된 경쟁사 앱 리뷰: {len(competitor_df)}건")
        
        return our_app_df, competitor_df
    
    def prepare_data_summary(self, our_app_df, competitor_df):
        """데이터 요약 생성"""
        
        # 플랫폼별 분리
        our_android = our_app_df[our_app_df['platform'] == 'android'] if len(our_app_df) > 0 else pd.DataFrame()
        our_ios = our_app_df[our_app_df['platform'] == 'ios'] if len(our_app_df) > 0 else pd.DataFrame()
        comp_android = competitor_df[competitor_df['platform'] == 'android'] if len(competitor_df) > 0 else pd.DataFrame()
        comp_ios = competitor_df[competitor_df['platform'] == 'ios'] if len(competitor_df) > 0 else pd.DataFrame()
        
        summary = {
            "our_app": {
                "total": len(our_app_df),
                "android": len(our_android),
                "ios": len(our_ios),
                "android_apps": our_android['package_name'].unique().tolist() if 'package_name' in our_android.columns and len(our_android) > 0 else [],
                "ios_apps": our_ios['app_id'].unique().tolist() if 'app_id' in our_ios.columns and len(our_ios) > 0 else []
            },
            "competitor": {
                "total": len(competitor_df),
                "android": len(comp_android),
                "ios": len(comp_ios),
                "android_apps": comp_android['package_name'].unique().tolist() if 'package_name' in comp_android.columns and len(comp_android) > 0 else [],
                "ios_apps": comp_ios['app_id'].unique().tolist() if 'app_id' in comp_ios.columns and len(comp_ios) > 0 else []
            },
            "date_range": {
                "start": min(
                    our_app_df['updated'].min() if len(our_app_df) > 0 and 'updated' in our_app_df.columns else datetime.now().isoformat(),
                    competitor_df['updated'].min() if len(competitor_df) > 0 and 'updated' in competitor_df.columns else datetime.now().isoformat()
                ),
                "end": max(
                    our_app_df['updated'].max() if len(our_app_df) > 0 and 'updated' in our_app_df.columns else datetime.now().isoformat(),
                    competitor_df['updated'].max() if len(competitor_df) > 0 and 'updated' in competitor_df.columns else datetime.now().isoformat()
                )
            }
        }
        return summary
    
    def create_analysis_prompt(self, our_app_df, competitor_df, summary):
        """Ollama에 전달할 프롬프트 생성"""
        
        # 샘플 데이터 생성 (전체 데이터가 너무 크면 샘플링)
        our_app_sample = our_app_df.head(200).to_dict('records') if len(our_app_df) > 0 else []
        competitor_sample = competitor_df.head(200).to_dict('records') if len(competitor_df) > 0 else []
        
        prompt = f"""당신은 데이터 분석 보고서를 전문적으로 작성하는 애널리스트입니다.  
아래 Android 및 iOS 리뷰 데이터를 기반으로 KB차차차(우리 서비스)의 리뷰를 먼저 분석하고, 이후 경쟁 서비스 HeyDealer와 비교하여 인사이트를 도출하는 1페이지 분량의 전문 리뷰 분석 보고서를 작성하세요.

보고서 목표
* 우리 서비스 KB차차차 앱 리뷰를 중심으로 먼저 분석한 뒤, 경쟁 서비스 HeyDealer 리뷰와 비교해 종합 인사이트를 도출합니다.
* 보고서 형식은 반드시 아래 제공하는 템플릿을 그대로 따라 작성하세요.
* 간결하지만 핵심 인사이트 중심의 전문 문체로 작성하세요.

입력 데이터 형식
리뷰 데이터 속성
* platform,author,rating,title,content,date,thumbs_up,developer_reply,app_identifier,ap_version

보고서 템플릿 (이 형식을 반드시 그대로 사용)

1. Executive Summary
* KB차차차 리뷰 기반 전체 경향 요약
* KB차차차의 강점 2~3개
* KB차차차의 개선 필요 영역 2~3개
* 최근 리뷰 증가/감소 트렌드
* 마지막 문단에서 HeyDealer 대비 핵심 차이 요약

2. 데이터 개요
* Android / iOS 리뷰 수 (KB차차차, HeyDealer)
* 분석 대상 앱 목록
* 수집 기간
* 주요 데이터 속성

3. 핵심 지표 비교 (KB차차차 vs HeyDealer)
* 플랫폼별 평균 평점
* 월간 리뷰 변화율
* 버전별 평점 변화
* 개발사 리뷰 응답률(Android 기준)
* 표 형태로 비교

4. 리뷰 내용 분석
* KB차차차 긍정 리뷰 주요 키워드
* KB차차차 부정 리뷰 주요 키워드
* 감성 비율(긍정/중립/부정)
* HeyDealer 대비 텍스트 패턴 차이 및 특징

5. 버전별/업데이트별 이슈
* KB차차차 특정 버전 이후 불만 증가 여부
* 평점 변동 포인트
* HeyDealer와 비교했을 때 발견되는 차이점

6. 개선 제안
* KB차차차 기능 개선 제안
* 운영/고객센터 대응 개선
* HeyDealer 대비 차별화 전략

출력 형식 규칙
* 전체 분량은 "A4 한 페이지" 기준으로 요약
* 불필요한 장황한 설명 금지
* 데이터 기반 인사이트 중심
* 표/리스트는 간결하게
* 주관적 표현 없이 분석 기반 서술
* 최종 결과만 말하고, 과정 설명 없음

=== 데이터 요약 ===
[KB차차차 (우리 회사 앱)]
- 총 리뷰 수: {summary['our_app']['total']}
- Android 리뷰: {summary['our_app']['android']}건
- iOS 리뷰: {summary['our_app']['ios']}건
- Android 앱: {', '.join(summary['our_app']['android_apps'][:3])}
- iOS 앱: {', '.join(summary['our_app']['ios_apps'][:3])}

[HeyDealer (경쟁사 앱)]
- 총 리뷰 수: {summary['competitor']['total']}
- Android 리뷰: {summary['competitor']['android']}건
- iOS 리뷰: {summary['competitor']['ios']}건
- Android 앱: {', '.join(summary['competitor']['android_apps'][:3])}
- iOS 앱: {', '.join(summary['competitor']['ios_apps'][:3])}

수집 기간: {summary['date_range']['start']} ~ {summary['date_range']['end']}

=== KB차차차 리뷰 샘플 (최대 200건) ===
{json.dumps(our_app_sample, ensure_ascii=False, indent=2)}

=== HeyDealer 리뷰 샘플 (최대 200건) ===
{json.dumps(competitor_sample, ensure_ascii=False, indent=2)}

위 데이터를 기반으로 KB차차차를 중심으로 분석하고, 후반부에 HeyDealer와 비교한 1페이지 분량의 전문 리뷰 분석 보고서를 작성하세요.
"""

        return prompt
    
    def call_ollama(self, prompt, model="llama3.2:latest"):
        """Ollama API 호출"""
        url = f"{self.ollama_url}/api/generate"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        print("\n=== Ollama AI 분석 시작 ===")
        print(f"모델: {model}")
        print(f"프롬프트 길이: {len(prompt)} 문자")
        
        try:
            response = requests.post(url, json=payload, timeout=900)
            response.raise_for_status()
            
            result = response.json()
            return result.get('response', '')
        
        except requests.exceptions.RequestException as e:
            print(f"Ollama API 호출 실패: {e}")
            return None
    
    def save_report(self, report, output_file="review_analysis_report.md"):
        """보고서 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_file.split('.')[0]}_{timestamp}.md"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n보고서가 저장되었습니다: {filename}")
        return filename
    
    def delete_processed_files(self):
        """처리된 파일 삭제"""
        deleted_count = 0
        
        for file in self.our_app_files + self.competitor_files:
            try:
                os.remove(file)
                deleted_count += 1
                print(f"삭제됨: {file}")
            except Exception as e:
                print(f"삭제 실패 ({file}): {e}")
        
        print(f"\n총 {deleted_count}개 파일 삭제 완료")
    
    def run(self, model="llama3.2:latest", delete_files=True):
        """전체 프로세스 실행"""
        print("=" * 60)
        print("앱 리뷰 분석 자동화 시스템 시작")
        print("=" * 60)
        
        # 1. 전달 파일 수집
        print("\n[1/6] 전달 데이터 파일 수집 중...")
        self.get_last_month_files()
        
        if not self.our_app_files and not self.competitor_files:
            print("분석할 파일이 없습니다.")
            return
        
        # 2. 데이터 로드 및 병합
        print("\n[2/6] 데이터 로드 및 병합 중...")
        our_app_df, competitor_df = self.load_and_merge_data()
        
        # 3. 데이터 요약 생성
        print("\n[3/6] 데이터 요약 생성 중...")
        summary = self.prepare_data_summary(our_app_df, competitor_df)
        
        # 4. 프롬프트 생성
        print("\n[4/6] 분석 프롬프트 생성 중...")
        prompt = self.create_analysis_prompt(our_app_df, competitor_df, summary)
        
        # 5. Ollama AI 분석
        print("\n[5/6] AI 분석 실행 중...")
        report = self.call_ollama(prompt, model)
        
        if report:
            # 6. 보고서 저장
            print("\n[6/6] 보고서 저장 중...")
            report_file = self.save_report(report)
            
            # 7. 파일 삭제
            if delete_files:
                print("\n처리된 파일 삭제 중...")
                self.delete_processed_files()
            
            print("\n" + "=" * 60)
            print("분석 완료!")
            print(f"보고서 위치: {report_file}")
            print("=" * 60)
        else:
            print("\nAI 분석 실패. 보고서를 생성할 수 없습니다.")


# 실행 예제
if __name__ == "__main__":
    # 분석기 초기화
    analyzer = ReviewAnalyzer(
        data_dir="./unified_review_data",
        ollama_url="http://localhost:11434"  # Ollama 서버 주소
    )
    
    # 분석 실행
    # model 옵션: "llama3.2:latest", "llama3:latest", "mistral:latest" 등
    # delete_files=True: 처리 후 파일 삭제, False: 파일 유지
    analyzer.run(
        model="gpt-oss:latest",
        delete_files=True
    )