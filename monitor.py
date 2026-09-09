import os
import requests
import json
from google import genai

# 環境変数の読み込み
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# Open-Meteo API (名古屋市役所付近の座標)
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
        "forecast_minutely_15": 12 # 今後3時間分
    }
    response = requests.get(url, params=params)
    return response.json()

def analyze_with_gemini(weather_data):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    以下は名古屋市の今後3時間の15分単位の気象予報データ(Open-Meteo)です。
    データ: {json.dumps(weather_data, ensure_ascii=False)}

    【指示】
    - 今後3時間以内に雨が降り始める、または急な強雨のリスクがあるか確認してください。
    - 降雨リスクがある場合のみ、Discord用の短く分かりやすいアラート文（絵文字付き、150文字程度）を作成してください。
    - 洗濯物の取り込みや傘の持参など、具体的なアクションをアドバイスしてください。
    - もし雨の心配が全くない場合は、文字列『NO_RAIN』とだけ回答してください。
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )
    return response.text.strip()

def send_discord_notification(message):
    payload = {"content": f"🌧️ **【名古屋市 雨雲接近アラート】**\n\n{message}"}
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def main():
    try:
        data = get_weather_data()
        
        # 簡易判定：今後3時間に少しでも降水予測があるかチェック
        minutely_precip = data.get("minutely_15", {}).get("precipitation", [])
        if any(p > 0.1 for p in minutely_precip):
            alert_message = analyze_with_gemini(data)
            if "NO_RAIN" not in alert_message:
                send_discord_notification(alert_message)
                print("Discord通知を送信しました。")
            else:
                print("雨リスクなしと判定されました。")
        else:
            print("降水予測なし（正常）")
            
    except Exception as e:
        print(f"エラー発生: {e}")

if __name__ == "__main__":
    main()
