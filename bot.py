import os
import json
import time
import feedparser
import datetime
import requests
from google import genai

# ==========================================
# 1. Config & Quotas
# ==========================================
DAILY_QUOTAS = {
    "AI": 8,
    "Medical": 5,
    "Tech": 5,
    "Space": 3,
    "Science": 2,
    "CyberSecurity": 2
}

RSS_SOURCES = [
    "https://www.theverge.com/rss/index.xml",
    "https://techcrunch.com/feed/",
    "https://www.sciencedaily.com/rss/top/technology.xml",
]

# ==========================================
# 2. Gemini Config (New SDK) & Debugger
# ==========================================
api_key = os.environ.get("GEMINI_API_KEY")

print("--------------------------------------------------")
if not api_key:
    print("❌ خطا: کلید GEMINI_API_KEY در گیت‌هاب پیدا نشد! (آیا آن را در بخش Secrets ذخیره کرده‌اید؟)")
else:
    print(f"✅ کلید جمینای پیدا شد. (۴ حرف آخر کلید شما: {api_key[-4:]})")
print("--------------------------------------------------")

client = genai.Client(api_key=api_key)
MODEL_ID = 'gemini-2.0-flash'

# ==========================================
# 3. State Management
# ==========================================
STATE_FILE = "daily_state.json"

def load_state():
    today = datetime.date.today().isoformat()
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            if state.get("date") == today:
                return state
            
    return {"date": today, "published_urls": [], "counts": {cat: 0 for cat in DAILY_QUOTAS}}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# ==========================================
# 4. AI Engine (Gemini)
# ==========================================
def categorize_news(title, summary):
    prompt = f"""
    Analyze the following news title and summary. 
    Categorize it strictly into ONE of the following categories:
    AI, Medical, Tech, Space, Science, CyberSecurity.
    
    CRITICAL RULE: If the content is an advertisement, a product deal, shopping advice, or discounts, you MUST output 'None'.
    If it doesn't fit the scientific categories, output 'None'.
    
    Title: {title}
    Summary: {summary}
    Output ONLY the category name.
    """
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt
    )
    category = response.text.strip()
    return category if category in DAILY_QUOTAS else None

def translate_and_format(title, content, date, link):
    prompt = f"""
    متن زیر را به فارسی روان، جذاب و ژورنالیستی ترجمه و خلاصه کن.
    از لحن مناسب برای یک کانال علمی استفاده کن.
    متن را با ایموجی‌های مرتبط تزئین کن.
    در انتهای متن، حتماً "تاریخ انتشار خبر" را (ترجیحاً به شمسی یا میلادی خوانا) بنویس.
    سپس ۳ تا ۵ هشتگ مرتبط فارسی قرار بده.
    در خط آخر، عبارت "🔗 منبع:" را بنویس و دقیقاً لینک خبر را مقابل آن قرار بده.

    عنوان خبر: {title}
    متن خبر: {content}
    تاریخ میلادی خبر: {date}
    لینک خبر: {link}
    """
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt
    )
    return response.text.strip()

# ==========================================
# 5. Bale API Publisher
# ==========================================
def send_to_channel(text):
    bot_token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("BALE_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("Error: BOT_TOKEN or BALE_CHAT_ID is missing in GitHub Secrets.")
        return False

    url = f"https://tapi.bale.ai/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("Successfully posted to Bale Channel!")
            return True
        else:
            print(f"Failed to post. API Response: {response.text}")
            return False
    except Exception as e:
        print(f"Network error while sending to Bale: {e}")
        return False

# ==========================================
# 6. Main Logic
# ==========================================
def main():
    state = load_state()
    
    all_articles = []
    for url in RSS_SOURCES:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            if entry.link not in state["published_urls"]:
                all_articles.append(entry)
                
    if not all_articles:
        print("No new articles found.")
        return

    published_in_this_run = False

    for article in all_articles:
        try:
            category = categorize_news(article.title, article.summary)
            time.sleep(6)
            
            if not category:
                continue
                
            if state["counts"][category] < DAILY_QUOTAS[category]:
                pub_date = getattr(article, 'published', getattr(article, 'updated', 'تاریخ نامشخص'))
                final_post = translate_and_format(article.title, article.summary, pub_date, article.link)
                success = send_to_channel(final_post)
                
                if success:
                    state["counts"][category] += 1
                    state["published_urls"].append(article.link)
                    save_state(state)
                    published_in_this_run = True
                    print(f"Posted in {category}. Remaining: {DAILY_QUOTAS[category] - state['counts'][category]}")
                    break 
                    
        except Exception as e:
            error_msg = str(e)
            print(f"🚨 خطای دقیق گوگل: {error_msg}") # چاپ خطای اصلی
            
            if "429" in error_msg or "quota" in error_msg.lower():
                print("API Rate Limit. Waiting 20 seconds...")
                time.sleep(20)
                continue
            else:
                continue

    if not published_in_this_run:
        print("No matching articles for remaining quotas in this run.")

if __name__ == "__main__":
    main()
