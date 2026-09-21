import os
import requests
from google import genai
from datetime import datetime, timedelta, timezone

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 名古屋市役所付近の座標
LATITUDE = 35.1815
LONGITUDE = 136.9066
JST = timezone(timedelta(hours=9))

# クールダウン時間（時間単位）: 1度通知したら2時間は通知しない
COOLDOWN_HOURS = 2
ALERT_LOG_FILE = "last_alert.txt"

def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "minutely_15": ["precipitation"],
        "hourly": ["precipitation_probability", "precipitation"],
        "models": "jma_seamless",
        "timezone": "Asia/Tokyo"
    }
    res = requests.get(url, params=params, timeout=10)
    res.raise_for_status()
    return res.json()

def analyze_with_gemini(upcoming_precip, upcoming_times):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    summary_data = [
        {"時刻": t, "予想降水量(mm)": p}
        for t, p in zip(upcoming_times, upcoming_precip)
    ]
    
    prompt = f"""
あなたは名古屋市の気象監視アシスタントです。
以下は名古屋市における【現在時刻以降の直近3時間】の15分ごと予想降水データです。
データ: {summary_data}

【要件】
1. 何時何分頃から雨が降り出すか（または強まるか）を分析してください。
2. Discord用のアラート文（150字程度、絵文字入り）を作成してください。
3. 傘が必要か、外出・洗濯物への影響など具体的なアドバイスを添えてください。
"""
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt
    )
    return response.text.strip()

def send_discord_notification(message):
    payload = {"content": f"🌧️ **【名古屋市 雨雲接近アラート】**\n\n{message}"}
    res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    res.raise_for_status()

def is_in_cooldown(now_jst):
    """前回通知から一定時間以内かどうかを判定"""
    if not os.path.exists(ALERT_LOG_FILE):
        return False
    
    try:
        with open(ALERT_LOG_FILE, "r") as f:
            last_alert_str = f.read().strip()
        last_alert_time = datetime.fromisoformat(last_alert_str)
        
        elapsed = now_jst - last_alert_time
        if elapsed < timedelta(hours=COOLDOWN_HOURS):
            remaining_mins = int((timedelta(hours=COOLDOWN_HOURS) - elapsed).total_seconds() // 60)
            print(f"クールダウン待機中: 前回の通知からまだ {int(elapsed.total_seconds() // 60)} 分しか経過していません（残り約 {remaining_mins} 分間通知を抑制）。")
            return True
    except Exception as e:
        print(f"クールダウン判定エラー（リセットします）: {e}")
        
    return False

def record_alert_time(now_jst):
    """通知した時刻をファイルに記録"""
    with open(ALERT_LOG_FILE, "w") as f:
        f.write(now_jst.isoformat())

def main():
    if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
        print("エラー: 必要な環境変数が未設定です。")
        return

    data = get_weather_data()
    minutely = data.get("minutely_15", {})
    raw_times = minutely.get("time", [])
    precip_list = minutely.get("precipitation", [])

    if not raw_times:
        print("気象データが取得できませんでした。")
        return

    now_jst = datetime.now(JST)
    current_time_str = now_jst.strftime("%Y-%m-%dT%H:%M")

    start_idx = 0
    for idx, t in enumerate(raw_times):
        if t >= current_time_str:
            start_idx = idx
            break

    end_idx = start_idx + 12
    upcoming_times = [t.split("T")[1] for t in raw_times[start_idx:end_idx]]
    upcoming_precip = precip_list[start_idx:end_idx]

    print(f"現在時刻: {current_time_str}")
    print(f"監視対象時刻: {upcoming_times}")
    print(f"予想降水量推移: {upcoming_precip}")

    has_rain = any(p is not None and p >= 0.1 for p in upcoming_precip)

    if has_rain:
        print("直近3時間以内の降雨を検知しました。")
        
        # クールダウン中かどうかチェック
        if is_in_cooldown(now_jst):
            print("通知はスキップします（クールダウン中）。")
            return

        print("Geminiで解析を実行します...")
        alert = analyze_with_gemini(upcoming_precip, upcoming_times)
        send_discord_notification(alert)
        record_alert_time(now_jst)
        print("Discordへ通知を送信し、送信時刻を記録しました。")
    else:
        print("直近3時間に降水予測はありません。待機します。")

if __name__ == "__main__":
    main()
