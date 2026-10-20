"""TikTok Carousel CLI Generator.

Can be run standalone by AI agents or users to produce a complete TikTok
photo-mode carousel with native rendered text in target languages.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add backend directory to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db import Session
from app.providers import ProviderError, generate_image, plan_content, refine_slide_prompt
from app.services import provider_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("carousel-cli")

# 11 Standard Target Markets & Default Languages
MARKETS: dict[str, tuple[str, str]] = {
    "US": ("美国", "美式英语（American English）"),
    "UK": ("英国", "英式英语（British English）"),
    "AU": ("澳大利亚", "澳大利亚英语（Australian English）"),
    "CA": ("加拿大", "加拿大英语（Canadian English）"),
    "MY": ("马来西亚", "马来语（Bahasa Melayu）"),
    "ID": ("印度尼西亚", "印尼语（Bahasa Indonesia）"),
    "TH": ("泰国", "泰语（ภาษาไทย）"),
    "PH": ("菲律宾", "菲律宾语（Filipino）"),
    "VN": ("越南", "越南语（Tiếng Việt）"),
    "SG": ("新加坡", "英语（English）"),
    "JP": ("日本", "日语（日本語）"),
}


def resolve_market_and_language(market_input: str, language_input: str | None = None) -> tuple[str, str]:
    cleaned = market_input.strip().upper()
    if cleaned in MARKETS:
        market_name, default_lang = MARKETS[cleaned]
    else:
        # Check by Chinese name
        match = next((v for v in MARKETS.values() if v[0] == market_input.strip()), None)
        if match:
            market_name, default_lang = match
        else:
            market_name = market_input.strip()
            default_lang = "美式英语（American English）"

    final_lang = language_input.strip() if language_input and language_input.strip() else default_lang
    return market_name, final_lang


def load_providers(args: argparse.Namespace) -> tuple[dict, dict]:
    analysis_provider = {}
    image_provider = {}

    try:
        with Session() as db:
            analysis_provider = provider_config(db, "analysis")
            image_provider = provider_config(db, "image")
    except Exception as e:
        log.warning("无法从本地数据库读取配置 (将检查环境变量与命令行参数): %s", e)

    # CLI / Env overrides
    if args.analysis_url:
        analysis_provider["base_url"] = args.analysis_url
    if args.analysis_key:
        analysis_provider["api_key"] = args.analysis_key
    if args.analysis_model:
        analysis_provider["model"] = args.analysis_model

    if args.image_url:
        image_provider["base_url"] = args.image_url
    if args.image_key:
        image_provider["api_key"] = args.image_key
    if args.image_model:
        image_provider["model"] = args.image_model
    if args.image_mode:
        image_provider["mode"] = args.image_mode

    if not analysis_provider.get("api_key") or not analysis_provider.get("model"):
        raise ValueError("缺少分析模型配置，请通过 --analysis-key/--analysis-model 或在 Web 界面中配置")
    if not args.plan_only and (not image_provider.get("api_key") or not image_provider.get("model")):
        raise ValueError("缺少生图模型配置，请通过 --image-key/--image-model 或在 Web 界面中配置")

    return analysis_provider, image_provider


def resolve_image_paths(images_arg: str | None) -> list[Path]:
    if not images_arg:
        return []
    paths: list[Path] = []
    for item in images_arg.split(","):
        item = item.strip()
        if not item:
            continue
        p = Path(item)
        if p.is_file():
            paths.append(p.resolve())
        elif p.is_dir():
            for f in sorted(p.iterdir()):
                if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    paths.append(f.resolve())
        else:
            log.warning("参考图片不存在: %s", item)
    return paths


async def run_pipeline(args: argparse.Namespace) -> dict:
    analysis_provider, image_provider = load_providers(args)
    market, language = resolve_market_and_language(args.market, args.language)
    ref_paths = resolve_image_paths(args.images)

    product = {
        "name": args.name,
        "description": args.desc or "",
        "category": args.category or "",
        "sku": args.sku or "",
        "features": args.features or "",
        "constraints": args.constraints or "",
        "price": args.price or "",
        "currency": args.currency or "",
    }

    out_dir = Path(args.out_dir or f"./carousel_{datetime.now().strftime('%Y%m%d_%H%M%S')}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Plan or Refine
    if args.refine_slide is not None:
        if not args.plan_file:
            raise ValueError("单图修订模式需提供 --plan-file 指向先前的 plan.json")
        plan_path = Path(args.plan_file).resolve()
        if not plan_path.is_file():
            raise FileNotFoundError(f"找不到策划文件: {plan_path}")
        with plan_path.open("r", encoding="utf-8") as f:
            plan = json.load(f)

        slide_idx = args.refine_slide - 1
        if not 0 <= slide_idx < len(plan["slides"]):
            raise IndexError(f"无效的 slide 编号: {args.refine_slide} (共 {len(plan['slides'])} 张)")

        target_slide = plan["slides"][slide_idx]
        log.info("正在为第 %d 张图片修订完整提示词...", args.refine_slide)
        refined = await refine_slide_prompt(
            analysis_provider,
            product,
            {"market": market, "language": language, "style": args.style, "brief": args.brief, "analysis": plan.get("analysis", {})},
            target_slide,
            instruction=args.instruction or "",
            reference_paths=ref_paths,
            image_mode=image_provider.get("mode", "reference"),
        )
        target_slide.update(refined)
        plan["slides"][slide_idx] = target_slide

        # Save updated plan
        (out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

        if args.plan_only:
            return {"status": "success", "mode": "plan_only_refine", "slide": target_slide, "plan_file": str(out_dir / "plan.json")}

        log.info("正在重新生成第 %d 张图片...", args.refine_slide)
        img_bytes = await generate_image(
            image_provider,
            target_slide["prompt"],
            ref_paths if image_provider.get("mode", "reference") == "reference" else [],
        )

        from PIL import Image
        img_out = out_dir / f"{args.refine_slide:02d}.jpg"
        with Image.open(io.BytesIO(img_bytes)) as im:
            im.convert("RGB").save(img_out, format="JPEG", quality=95)

        return {
            "status": "success",
            "mode": "single_image_refined",
            "slide_index": args.refine_slide,
            "image_path": str(img_out),
            "prompt": target_slide["prompt"],
        }

    # Standard full carousel generation
    log.info("正在由 AI 视觉操盘手策划 TikTok 轮播故事线 (目标市场: %s, 语言: %s, 风格: %s, 共 %d 张)...", market, language, args.style, args.count)
    plan = await plan_content(
        analysis_provider,
        product,
        market=market,
        language=language,
        image_count=args.count,
        style=args.style,
        brief=args.brief or "",
        reference_paths=ref_paths,
        image_mode=image_provider.get("mode", "reference"),
    )

    # Save plan.json and caption.txt
    (out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    tags_str = ' '.join(f"#{t.lstrip('#')}" for t in plan.get('tags', []))
    caption_content = f"{plan.get('caption', '')}\n\n{tags_str}"
    (out_dir / "caption.txt").write_text(caption_content, encoding="utf-8")

    if args.plan_only:
        log.info("策划已保存至 %s (plan-only 模式，未调用生图)", out_dir / "plan.json")
        return {
            "status": "success",
            "mode": "plan_only",
            "out_dir": str(out_dir),
            "title": plan.get("title"),
            "caption": plan.get("caption"),
            "tags": plan.get("tags"),
            "slides": plan.get("slides"),
        }

    log.info("开始并发生成 %d 张包含原生文字的 TikTok 轮播图片...", len(plan["slides"]))
    concurrency = max(1, min(int(image_provider.get("concurrency", 2)), 4))
    sem = asyncio.Semaphore(concurrency)

    from PIL import Image

    async def generate_single(index: int, slide: dict) -> dict:
        async with sem:
            log.info("正在生成图片 [%d/%d]: %s", index + 1, len(plan["slides"]), slide["title"])
            raw = await generate_image(
                image_provider,
                slide["prompt"],
                ref_paths if image_provider.get("mode", "reference") == "reference" else [],
            )
            raw_path = out_dir / f"{index + 1:02d}.png"
            jpg_path = out_dir / f"{index + 1:02d}.jpg"
            with Image.open(io.BytesIO(raw)) as im:
                im.convert("RGB").save(raw_path, format="PNG")
                im.convert("RGB").save(jpg_path, format="JPEG", quality=95)
            return {
                "position": index + 1,
                "title": slide["title"],
                "body": slide["body"],
                "image_jpg": str(jpg_path),
                "image_png": str(raw_path),
                "prompt": slide["prompt"],
            }

    tasks = [generate_single(i, slide) for i, slide in enumerate(plan["slides"])]
    results = await asyncio.gather(*tasks)

    log.info("整套图文生成完成！文件已存入: %s", out_dir)
    return {
        "status": "success",
        "mode": "full_carousel",
        "out_dir": str(out_dir),
        "title": plan.get("title"),
        "caption": plan.get("caption"),
        "tags": plan.get("tags"),
        "caption_file": str(out_dir / "caption.txt"),
        "plan_file": str(out_dir / "plan.json"),
        "slides": results,
    }


def main():
    parser = argparse.ArgumentParser(description="TikTok Carousel CLI Generator")
    parser.add_argument("--name", required=True, help="商品名称")
    parser.add_argument("--desc", default="", help="商品描述/用途/场景")
    parser.add_argument("--features", default="", help="真实卖点/规格参数")
    parser.add_argument("--constraints", default="", help="禁用词/避坑约束")
    parser.add_argument("--category", default="", help="商品分类")
    parser.add_argument("--sku", default="", help="商品SKU")
    parser.add_argument("--price", default="", help="价格")
    parser.add_argument("--currency", default="", help="币种")
    parser.add_argument("--images", default="", help="参考图路径列表(逗号分隔)或文件夹")
    parser.add_argument("--market", default="MY", help="目标市场代号(如 MY, US, UK, ID, TH, VN, SG, JP)或中文名")
    parser.add_argument("--language", default="", help="内容语言(留空则按市场自动匹配)")
    parser.add_argument("--count", type=int, default=6, help="图片张数(4-10)")
    parser.add_argument("--style", default="生活方式", help="视觉风格")
    parser.add_argument("--brief", default="", help="额外的创作简报/受众说明")
    parser.add_argument("--out-dir", default="", help="输出目录")
    parser.add_argument("--plan-only", action="store_true", help="只输出策划与提示词，不实际调用生图")
    parser.add_argument("--refine-slide", type=int, default=None, help="单图重生成编号(1-based)")
    parser.add_argument("--instruction", default="", help="单图重生成调整说明")
    parser.add_argument("--plan-file", default="", help="已有策划 plan.json 路径(单图重生成必须提供)")

    parser.add_argument("--analysis-url", default=None, help="覆盖分析模型 Base URL")
    parser.add_argument("--analysis-key", default=None, help="覆盖分析模型 API Key")
    parser.add_argument("--analysis-model", default=None, help="覆盖分析模型名称")
    parser.add_argument("--image-url", default=None, help="覆盖生图模型 Base URL")
    parser.add_argument("--image-key", default=None, help="覆盖生图模型 API Key")
    parser.add_argument("--image-model", default=None, help="覆盖生图模型名称")
    parser.add_argument("--image-mode", choices=["reference", "background"], default=None, help="生图模式")

    args = parser.parse_args()

    try:
        result = asyncio.run(run_pipeline(args))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        log.error("执行失败: %s", e)
        print(json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
