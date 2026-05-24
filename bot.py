import os
import json
import time
import feedparser
import datetime
import requests
import google.generativeai as genai

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

# Gemini Config
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# ==========================================
# 2. State Management
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
# 3. AI Engine (Gemini)
# ==========================================
def categorize_news(title, summary):
    prompt = f"""
    Analyze the following news title and summary. 
    Categorize it strictly into ONE of the following categories:
    AI, Medical, Tech, Space, Science, CyberSecurity.
    If it doesn't fit well, output 'None'.
    Title: {title}
    Summary: {summary}
    Output ONLY the category name.
    """
    response = model.generate_content(prompt)
    category = response.text.strip()
    return category if category in DAILY_QUOTAS else None

def translate_and_format(title, content):
    prompt = f"""
    متن زیر را به فارسی روان، جذاب و ژورنالیستی ترجمه و خلاصه کن.
    از لحن مناسب برای یک کانال تلگرامی/بله علمی استفاده کن.
    متن را با ایموجی‌های مرتبط تزئین کن و در انتها ۳ تا ۵ هشتگ مرتبط فارسی قرار بده.
    عنوان خبر: {title}
    متن خبر: {content}
    """
    response = model.generate_content(prompt)
    return response.text.strip()

# ==========================================
# 4. Channel Publisher
# ==========================================
def send_to_channel(text):
    print(f"--- POSTING TO CHANNEL ---\n{text}\n--------------------------")
    return True

# ==========================================
# 5. Main Logic
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
            
            time.sleep(4)
            
            if not category:
                continue
                
            if state["counts"][category] < DAILY_QUOTAS[category]:
                final_post = translate_and_format(article.title, article.summary)
                
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
            if "429" in error_msg or "Quota" in error_msg:
                print("API Rate Limit. Waiting 10 seconds...")
                time.sleep(10)
                continue
            else:
                print(f"Unknown Error: {error_msg}")
                continue

    if not published_in_this_run:
        print("No matching articles for remaining quotas in this run.")

if __name__ == "__main__":
    main()
