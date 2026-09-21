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
3. 雨のリスクが皆無の場合は、余計な文字を含めず「NO_RAIN」とだけ返答してください。
"""
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt
    )
    return response.text.strip()

def send_discord_notification(message):
    payload = {"content": message}
    res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    res.raise_for_status()

def main():
    if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
        print("エラー: 必要な環境変数が設定されていません。")
        return

    data = get_weather_data()
    
    # ----------------------------------------------------
    # テスト用強制発砲ロジック
    # ----------------------------------------------------
    print("【テスト実行】強制的にGemini解析とDiscord送信を行います...")
    alert = analyze_with_gemini(data)
    
    if "NO_RAIN" in alert:
        test_message = f"🧪 **【動作テスト：雨雲接近監視Bot】**\n現在、直近3時間の名古屋市内に雨の予測はありません（通常運用時はこのメッセージは送信されず静止します）。システム連携は正常です！"
    else:
        test_message = f"🧪 **【動作テスト：雨雲接近監視Bot】**\n\n{alert}"
        
    send_discord_notification(test_message)
    print("Discordへテスト通知を送信しました。")

if __name__ == "__main__":
    main()
