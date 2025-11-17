import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

sender_email = "butterbutter030@gmail.com"
receiver_email = "htoh702@kbfg.com"
password = "xhfuaqlhvtjociks"

msg = MIMEMultipart()
msg["From"] = sender_email
msg["To"] = receiver_email
msg["Subject"] = "어플 댓글 자료 전달"

body = "첨부된 CSV 파일을 확인해주세요."
msg.attach(MIMEText(body, "plain"))


file1_path = "kb_chachacha_google_reviews.csv"
file2_path = "kb_chachacha_ios_reviews.csv"

if os.path.exists(file1_path):
    with open(file1_path, "rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(file1_path)}")
    msg.attach(part)
else:
    print("⚠️ CSV 파일이 존재하지 않습니다.")

if os.path.exists(file2_path):
    with open(file2_path, "rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(file2_path)}")
    msg.attach(part)
else:
    print("⚠️ CSV 파일이 존재하지 않습니다.")


try:
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender_email, password)
    server.send_message(msg)
    print("✅ 이메일이 성공적으로 전송되었습니다.")
except Exception as e:
    print(f"❌ 오류 발생: {e}")
finally:
    server.quit()
