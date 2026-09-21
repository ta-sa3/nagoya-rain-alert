import os
import requests
import json
from google import genai
from datetime import datetime, timedelta, timezone

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 名古屋市役所付近の座標
LATITUDE = 35.1815
LONGITUDE = 136.9066
JST = timezone(timedelta(hours=9))

# 設定パラメータ
COOLDOWN_HOURS = 2          # 基本のクールダウン時間（時間単位）
HEAVY_RAIN_THRESHOLD = 5.0  # ゲリラ豪雨と判定する15分あたり降水量閾値 (mm/15min)
ALERT_LOG_FILE = "last_alert.json"

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

def analyze_with_gemini(upcoming_precip, upcoming_times, is_urgent=False):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    summary_data = [
        {"時刻": t, "予想降水量(mm)": p}
        for t, p in zip(upcoming_times, upcoming_precip)
    ]
    
    urgent_instruction = ""
    if is_urgent:
        urgent_instruction = "【重要】急激な雨雲の発達・ゲリラ豪雨のリスクが高まっています。冒頭に緊急性を強調し、浸水・落雷・突風への警戒を呼びかけてください。"

    prompt = f"""
あなたは名古屋市の気象監視アシスタントです。
以下は名古屋市における【現在時刻以降の直近3時間】の15分ごと予想降水データです。
データ: {summary_data}

{urgent_instruction}

【要件】
1. 何時何分頃から雨が降り出すか（または強まるか）を分析してください。
2. Discord用のアラート文（150〜200字程度、絵文字入り）を作成してください。
3. 傘の準備だけでなく、外出の見合わせや地下・河川の注意など状況に応じたアドバイスを添えてください。
"""
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt
    )
    return response.text.strip()

def send_discord_notification(message, is_urgent=False):
    title = "🚨 **【緊急・ゲリラ豪雨警報】名古屋市 雨雲急発達**" if is_urgent else "🌧️ **【名古屋市 雨雲接近アラート】**"
    payload = {"content": f"{title}\n\n{message}"}
    res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    res.raise_for_status()

def check_cooldown_and_urgency(now_jst, max_current_precip):
    """
    クールダウン中かどうか、およびゲリラ豪雨による割り込みが必要かを判定。
    戻り値: (should_alert: bool, is_urgent: bool)
    """
    if not os.path.exists(ALERT_LOG_FILE):
        # 過去ログがない場合は通常通知
        return True, (max_current_precip >= HEAVY_RAIN_THRESHOLD)

    try:
        with open(ALERT_LOG_FILE, "r") as f:
            log_data = json.load(f)

        last_alert_time = datetime.fromisoformat(log_data.get("timestamp"))
        last_max_precip = log_data.get("max_precip", 0.0)

        elapsed = now_jst - last_alert_time
        in_cooldown = elapsed < timedelta(hours=COOLDOWN_HOURS)

        # ゲリラ豪雨割り込み判定:
        # クールダウン中であっても、今回の雨量が閾値(5.0mm/15分)以上で、かつ前回の通知時より激しい場合
        if in_cooldown and (max_current_precip >= HEAVY_RAIN_THRESHOLD) and (max_current_precip > last_max_precip * 1.5):
            print(f"⚠️ 緊急割り込み発生！ 降水量が急増 ({last_max_precip}mm -> {max_current_precip}mm)。クールダウンをバイパスします。")
            return True, True

        if in_cooldown:
            remaining = int((timedelta(hours=COOLDOWN_HOURS) - elapsed).total_seconds() // 60)
            print(f"クールダウン待機中: 前回の通知から {int(elapsed.total_seconds() // 60)} 分経過（残り {remaining} 分待機）。")
            return False, False

        return True, (max_current_precip >= HEAVY_RAIN_THRESHOLD)

    except Exception as e:
        print(f"ログ読み込み例外（通知を許可します）: {e}")
        return True, False

def record_alert_data(now_jst, max_current_precip):
    """通知時の時刻と最大降水量をJSONで記録"""
    data = {
        "timestamp": now_jst.isoformat(),
        "max_precip": max_current_precip
    }
    with open(ALERT_LOG_FILE, "w") as f:
        json.dump(data, f)

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
    upcoming_precip = [p if p is not None else 0.0 for p in precip_list[start_idx:end_idx]]

    print(f"現在時刻: {current_time_str}")
    print(f"監視対象時刻: {upcoming_times}")
    print(f"予想降水量推移: {upcoming_precip}")

    max_precip = max(upcoming_precip) if upcoming_precip else 0.0

    # 0.1mm以上の降水があるか
    if max_precip >= 0.1:
        print(f"降雨予測を検知（最大: {max_precip}mm/15min）")
        
        should_alert, is_urgent = check_cooldown_and_urgency(now_jst, max_precip)
        
        if not should_alert:
            print("通知条件を満たさないためスキップします。")
            return

        print(f"Gemini解析を実行します (緊急モード: {is_urgent})...")
        alert = analyze_with_gemini(upcoming_precip, upcoming_times, is_urgent=is_urgent)
        send_discord_notification(alert, is_urgent=is_urgent)
        record_alert_data(now_jst, max_precip)
        print("Discord通知を完了し、ログを更新しました。")
    else:
        print("直近3時間に降水予測はありません。待機します。")

if __name__ == "__main__":
    main()
