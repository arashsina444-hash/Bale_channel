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
# 2. Gemini Config & Deep Scanner
# ==========================================
api_key = os.environ.get("GEMINI_API_KEY")

print("--------------------------------------------------")
if not api_key:
    print("❌ خطا: کلید GEMINI_API_KEY پیدا نشد!")
else:
    print(f"✅ کلید متصل شد. (۴ حرف آخر: {api_key[-4:]})")
print("--------------------------------------------------")

client = genai.Client(api_key=api_key) if api_key else None
MODEL_ID = None

def find_working_model():
    print("🔍 در حال بررسی لیست مدل‌های مجاز و تست سهمیه رایگان...")
    try:
        available_models = [m.name.replace('models/', '') for m in client.models.list()]
        
        preferred_order = [
            'gemini-2.5-flash-lite',
            'gemini-flash-lite-latest',
            'gemini-2.5-flash',
            'gemini-flash-latest',
            'gemini-3.5-flash'
        ]
        
        models_to_test = [p for p in preferred_order if p in available_models]
        
        for m in available_models:
            if 'flash' in m and m not in models_to_test and 'preview' not in m:
                models_to_test.append(m)
                
        for m in models_to_test:
            print(f"⏳ در حال تست سهمیه مدل: {m} ...")
            try:
                client.models.generate_content(model=m, contents="hi")
                print(f"🎯 مدل {m} با موفقیت تست شد و انتخاب شد!")
                return m
            except Exception as e:
                err = str(e)
                if "limit: 0" in err:
                    pass
                elif "429" in err or "quota" in err.lower():
                    print(f"✅ مدل {m} فعال است (محدودیت سرعت لحظه‌ای). انتخاب شد.")
                    return m
            time.sleep(2)
            
        print("🚨 هیچ‌کدام از مدل‌ها سهمیه رایگان نداشتند!")
        return None
        
    except Exception as e:
        print(f"🚨 خطای دریافت لیست: {e}")
        return None

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
# 4. Smart Local Categorizer (Zero API Cost)
# ==========================================
def categorize_news(title, summary):
    text = f" {title} {summary} ".lower()
    
    # 1. فیلتر کردن تبلیغات
    ads_keywords = [" deal ", " discount ", " sale ", " save $", " price drop ", " buy now ", " coupon ", " % off "]
    if any(ad in text for ad in ads_keywords):
        return None
        
    # 2. جستجوی کلمات کلیدی دسته‌بندی‌ها
    categories = {
        "AI": [" artificial intelligence", " ai ", "machine learning", "chatgpt", "gemini", "openai", "neural network", " llm ", "deep learning"],
        "CyberSecurity": [" hacker ", "cybersecurity", "malware", "ransomware", "vulnerability", "breach", "cyber attack", " password"],
        "Space": [" space ", "nasa", "spacex", " mars ", " moon ", "galaxy", "telescope", "astronaut", "orbit"],
        "Medical": [" health", " medical", " cancer", "disease", "medicine", " brain", "vaccine", "clinical", "hospital"],
        "Tech": [" apple ", " google ", " microsoft ", "smartphone", "laptop", " android ", " ios ", "gadget", "processor", "hardware"],
        "Science": ["physics", "chemistry", "biology", "fossil", "archaeology", "quantum", "scientist", "climate"]
    }
    
    for cat, keywords in categories.items():
        if any(kw in text for kw in keywords):
            return cat
            
    return None

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
        print("Error: BOT_TOKEN or BALE_CHAT_ID is missing.")
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
    if not client:
        return
        
    global MODEL_ID
    MODEL_ID = find_working_model()
    
    if not MODEL_ID:
        print("🚨 برنامه متوقف شد.")
        return
        
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
        # دسته‌بندی کاملا رایگان و محلی انجام می‌شود
        category = categorize_news(article.title, article.summary)
        
        if not category:
            continue
            
        if state["counts"][category] < DAILY_QUOTAS[category]:
            try:
                print(f"خبر مرتبط با {category} پیدا شد. در حال ارسال به جمینای برای ترجمه...")
                pub_date = getattr(article, 'published', getattr(article, 'updated', 'تاریخ نامشخص'))
                
                # مصرف سهمیه گوگل فقط در این خط اتفاق می‌افتد
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
                print(f"🚨 خطای ارسال در حین ترجمه: {error_msg}")
                if "429" in error_msg or "quota" in error_msg.lower():
                    print("API Rate Limit. برنامه متوقف می‌شود تا در اجرای بعدی تلاش کند.")
                    break # خروج از حلقه برای جلوگیری از مسدودی بیشتر
                else:
                    continue

    if not published_in_this_run:
        print("No matching articles for remaining quotas in this run.")

if __name__ == "__main__":
    main()
