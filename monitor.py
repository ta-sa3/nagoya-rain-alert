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

def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast"
    # 日本気象庁シームレスモデル(jma_seamless)と高解像度15分データを取得
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

    # 現在時刻 (JST) を作成
    now_jst = datetime.now(JST)
    current_time_str = now_jst.strftime("%Y-%m-%dT%H:%M")

    # 現在時刻以降のインデックスを探す
    start_idx = 0
    for idx, t in enumerate(raw_times):
        if t >= current_time_str:
            start_idx = idx
            break

    # 直近3時間分（15分刻みで12個分）を正しく切り出し
    end_idx = start_idx + 12
    upcoming_times = [t.split("T")[1] for t in raw_times[start_idx:end_idx]]
    upcoming_precip = precip_list[start_idx:end_idx]

    print(f"現在時刻: {current_time_str}")
    print(f"監視対象時刻: {upcoming_times}")
    print(f"予想降水量推移: {upcoming_precip}")

    # 直近3時間で0.1mm以上の雨があるか判定
    has_rain = any(p is not None and p >= 0.1 for p in upcoming_precip)

    if has_rain:
        print("直近3時間以内の降雨を検知！Geminiで解析します...")
        alert = analyze_with_gemini(upcoming_precip, upcoming_times)
        send_discord_notification(alert)
        print("Discordへ通知を送信しました。")
    else:
        print("直近3時間に降水予測はありません。待機します。")

if __name__ == "__main__":
    main()
