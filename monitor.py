import os
import requests
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 名古屋市役所付近の座標
LATITUDE = 35.1815
LONGITUDE = 136.9066

def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "minutely_15": ["precipitation", "rain"],
        "hourly": ["relative_humidity_2m", "wind_speed_10m"],
        "timezone": "Asia/Tokyo",
        "forecast_minutely_15": 12  # 直近3時間分 (15分単位)
    }
    res = requests.get(url, params=params, timeout=10)
    res.raise_for_status()
    return res.json()

def analyze_with_gemini(weather_data):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
あなたは気象監視アシスタントです。
以下は名古屋市の今後3時間（15分刻み）の予報データです。
データ: {weather_data}

【要件】
1. 今後3時間以内に雨が降り出す、または強まる兆候があるかを判定してください。
2. 雨が予想される場合は、Discord用の注意喚起メッセージ（150字程度、絵文字入り）を作成してください。いつ頃傘が必要か、洗濯物の注意点を含めてください。
3. 雨のリスクが皆無、または影響が極めて軽微な場合は、余計な文字を含めず「NO_RAIN」とだけ返答してください。
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
        print("エラー: 必要な環境変数が設定されていません。")
        return

    data = get_weather_data()
    minutely_precip = data.get("minutely_15", {}).get("precipitation", [])

    # 直近3時間に 0.1mm 以上の降水予測があるかチェック（防波堤判定）
    has_rain = any(p is not None and p > 0.1 for p in minutely_precip)

    if has_rain:
        print("降雨予測を検知しました。Geminiで解析を実行します...")
        alert = analyze_with_gemini(data)
        
        if "NO_RAIN" not in alert:
            send_discord_notification(alert)
            print("Discordへ雨雲アラートを送信しました。")
        else:
            print("Gemini解析結果: 降雨影響なし (NO_RAIN)")
    else:
        print("直近3時間の降水予測はありません。API消費をスキップして終了します。")

if __name__ == "__main__":
    main()
