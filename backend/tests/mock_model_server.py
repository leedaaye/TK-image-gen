"""Manual browser smoke-test model. Local test only; never configure for real work."""
import base64
import io
import json
from fastapi import FastAPI, Request
from PIL import Image, ImageDraw

app = FastAPI()


@app.post('/v1/chat/completions')
async def chat(request: Request):
    body = await request.json()
    content = body['messages'][-1]['content']
    count = 4
    if isinstance(content, list):
        data = json.loads(content[0]['text'])
        count = data['image_count']
    result = {'title': 'Daily Carry · 蓝色随行杯', 'caption': 'Make room for simple daily routines.', 'tags': ['#DailyCarry', '#TravelCup'], 'analysis': {'supported_facts': ['蓝色随行杯'], 'missing_information': ['容量与材质未提供，不作宣传'], 'cautions': ['本项目为本地模拟接口验证']}, 'slides': [{'title': title, 'body': 'A small companion for your everyday routine.', 'prompt': 'A blue travel cup in natural daylight, clean neutral backdrop, leave lower area clear.'} for title in ['Your everyday companion', 'Made for your routine', 'A closer look', 'Find your new favorite', 'Simple daily moments', 'Discover more', 'Details matter', 'Take it along', 'A fresh start', 'Your next chapter'][:count]]}
    return {'choices': [{'message': {'content': json.dumps(result)}}]}


@app.post('/v1/images/edits')
@app.post('/v1/images/generations')
async def image():
    target = Image.new('RGB', (768, 1024), '#e8e8df')
    draw = ImageDraw.Draw(target)
    draw.ellipse((90, 670, 680, 820), fill='#d4d7cf')
    draw.rounded_rectangle((260, 230, 510, 740), radius=65, fill='#527e91')
    draw.rounded_rectangle((245, 205, 525, 280), radius=30, fill='#324f5b')
    draw.rounded_rectangle((285, 300, 310, 650), radius=12, fill='#719aaa')
    buffer = io.BytesIO()
    target.save(buffer, 'PNG')
    return {'data': [{'b64_json': base64.b64encode(buffer.getvalue()).decode()}]}
