import os
import io
import pandas as pd
import requests
from docx import Document
from datetime import datetime, timedelta

# -------------------------------------------------------------------
# 1. CSV(analysis 파일) 파싱: "### 섹션" 단위로 끊어서 DataFrame으로 읽기
# -------------------------------------------------------------------

def parse_analysis_csv(path: str) -> dict:
    """
    analysis/*.csv 파일을 파싱해서
    {
        "platform_review_count": DataFrame,
        "rating_distribution": DataFrame,
        "top5_likes": DataFrame,
        "version_rating_top5": DataFrame,
    }
    형태의 dict로 반환
    """
    sections = {}
    current_section = None
    current_lines = []

    with open(path, "r", encoding="utf-8-sig") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                # 빈 줄은 그냥 넘어감
                continue

            if line.startswith("### "):
                # 이전 섹션 저장
                if current_section is not None and current_lines:
                    csv_text = "\n".join(current_lines)
                    df = pd.read_csv(io.StringIO(csv_text))
                    sections[current_section] = df
                    current_lines = []

                # 새 섹션 시작
                current_section = line.replace("###", "").strip()
            else:
                # 섹션 안의 CSV 라인
                current_lines.append(line)

        # 마지막 섹션 저장
        if current_section is not None and current_lines:
            csv_text = "\n".join(current_lines)
            df = pd.read_csv(io.StringIO(csv_text))
            sections[current_section] = df

    return sections


# -------------------------------------------------------------------
# 2. LLM에 넘길 데이터 블록 만들기 (CSV 형식 그대로 / 섹션별)
# -------------------------------------------------------------------

def build_data_block(app_name: str, sections: dict) -> str:
    """
    한 앱(kbchachacha / heydealer / encar)에 대한 섹션 dict를
    프롬프트에 넣기 좋은 텍스트 블록으로 변환
    """
    lines = [f"#### APP: {app_name}"]

    # 섹션 순서 고정 (보고서 형식 consistency를 위해)
    section_order = [
        "platform_review_count",
        "rating_distribution",
        "top5_likes",
        "version_rating_top5",
    ]

    for key in section_order:
        if key not in sections:
            continue
        df = sections[key]
        lines.append(f"[SECTION] {key}")
        # LLM이 보기 좋게 CSV 형태로 전달
        csv_text = df.to_csv(index=False)
        lines.append(csv_text.strip())  # 마지막 개행 제거
        lines.append("")  # 섹션 사이 빈 줄

    return "\n".join(lines)


# -------------------------------------------------------------------
# 3. Ollama(gpt-oss)에게 보낼 시스템 프롬프트 & 유저 프롬프트 템플릿
# -------------------------------------------------------------------

SYSTEM_PROMPT = """
당신은 중고차 앱 리뷰 데이터를 분석하는 데이터 애널리스트입니다.

반드시 아래 규칙을 지키세요.

1. 오직 '데이터 블록'에 포함된 정보만 사용해서 분석합니다.
2. 외부 지식, 일반적인 상식, 과거 경험, 인터넷 정보는 절대 사용하지 않습니다.
3. 데이터에 명시적으로 존재하지 않는 내용은 추측하지 말고 반드시 '데이터에 없음'이라고 적습니다.
4. 요청이 여러 번 오더라도, 항상 아래의 보고서 형식과 섹션 제목을 그대로 사용합니다.
5. 모든 내용은 한국어로 작성합니다.

[보고서 형식]

# 1. 요약
- 세 앱(KB차차차, 헤이딜러, 엔카)의 전반적인 비교 요약 (2~3문장)

# 2. 플랫폼별 리뷰 규모 비교
- 세 앱의 플랫폼(Android/iOS)별 리뷰 수를 비교
- 상대적인 규모, 편중 여부 언급 (각 2~3문장)

# 3. 평점 분포 비교
- 각 앱의 평점 분포(1~5점)를 비교
- '어느 앱이 상대적으로 평점이 높은 편인지'를 데이터 범위 내에서만 설명

# 4. 좋아요 Top5 리뷰 인사이트
- 각 앱의 Top5 리뷰 내용을 요약
- 사용자들이 중요하게 생각하는 포인트를 비교
- 추측 금지, 실제 리뷰 내용에서만 뽑아서 정리

# 5. 버전별 품질 이슈 및 강점
- 버전별 평균 평점/리뷰 수 상위 Top5 데이터를 기반으로
  품질이 상대적으로 좋은 버전/나쁜 버전을 간단히 언급
- '추세'는 데이터가 허용하는 범위 내에서만 언급

# 6. KB차차차 관점의 전략 제언
- 위의 비교 결과를 기반으로 KB차차차가 취할 수 있는 전략을 3~5개 Bullet로 정리
- 여기도 '데이터에 기반한 내용'만 적고, 데이터에 없는 내용은 적지 않음

전체 분량은 A4 1장 이내, 각 섹션은 2~5문장 정도로 간결하게 작성하세요.
"""

USER_PROMPT_TEMPLATE = """
아래는 우리 회사 서비스 KB차차차와 경쟁사 헤이딜러, 엔카의 리뷰 분석 요약 데이터입니다.

[데이터 시작]
{data_block}
[데이터 끝]

위 데이터를 기반으로, 'KB차차차 vs 헤이딜러 vs 엔카' 비교 분석 보고서를 작성하세요.
반드시 시스템 프롬프트에 정의된 보고서 형식과 규칙을 지키세요.
"""


# -------------------------------------------------------------------
# 4. Ollama(gpt-oss) 호출 함수
# -------------------------------------------------------------------

def call_ollama_gpt_oss(system_prompt: str, user_prompt: str, model: str = "gpt-oss") -> str:
    """
    Ollama /api/chat 엔드포인트로 gpt-oss 모델에 요청.
    """
    url = "http://localhost:11434/api/chat"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "temperature": 0.3,
            "num_predict": 2000
        },
        "stream": False,
    }

    resp = requests.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()

    # Ollama chat 응답 형식: {"message": {"role": "...", "content": "..."}, ...}
    return data["message"]["content"]

def save_report_as_docx(report_text: str, output_path: str = "./analysis_report.docx"):
    doc = Document()
    for line in report_text.split("\n"):
        doc.add_paragraph(line)
    doc.save(output_path)
    print(f"[OK] Word 파일로 저장 완료 → {output_path}")


def save_report(report):
    """보고서 저장"""
    os.makedirs("./analysis", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"analysis_report_{timestamp}.md"
    filepath = os.path.join("./analysis", filename)
        
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(report)
        
    print(f"\n보고서가 저장되었습니다: {filename}")
    return filename

# -------------------------------------------------------------------
# 5. 전체 파이프라인: CSV 읽고 → 프롬프트 만들고 → 보고서 생성
# -------------------------------------------------------------------

def main():
    base_dir = "./analysis"
    app_files = {
        "kbchachacha": os.path.join(base_dir, "kbchachacha_analysis.csv"),
        "heydealer": os.path.join(base_dir, "heydealer_analysis.csv"),
        "encar": os.path.join(base_dir, "encar_analysis.csv"),
    }

    # 앱별 데이터 블록 만들기
    app_blocks = []
    for app_name, path in app_files.items():
        if not os.path.exists(path):
            print(f"[WARN] 파일 없음: {path}")
            continue
        sections = parse_analysis_csv(path)
        block = build_data_block(app_name, sections)
        app_blocks.append(block)

    if not app_blocks:
        raise RuntimeError("분석할 CSV 파일이 없습니다.")

    # 세 앱 데이터 블록을 하나로 합침
    combined_data_block = "\n\n".join(app_blocks)

    # 유저 프롬프트 생성
    user_prompt = USER_PROMPT_TEMPLATE.format(data_block=combined_data_block)

    # Ollama 호출
    report = call_ollama_gpt_oss(SYSTEM_PROMPT, user_prompt)

    # 결과 출력
    save_report(report)


if __name__ == "__main__":
    main()
