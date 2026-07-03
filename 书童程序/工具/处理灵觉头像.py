#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
处理灵觉/PROME 师兄形象素材：
1. 从机器人全身图提取头部作为头像（方形+圆形）
2. 从标志图提取透明底圆环+文字
3. 合成标志到机器人胸口
输出全部放到 临时交付/
"""

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from pathlib import Path
import numpy as np
from scipy import ndimage

ROOT = Path("/Users/lingjue/Documents/shutong")
OUT = ROOT / "临时交付"
OUT.mkdir(parents=True, exist_ok=True)

ROBOT_SRC = Path("/Users/lingjue/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wsywmlqy_56af/temp/RWTemp/2026-06/0d674d9d01be0014c8990f2f470dc501/a6ddb501f170ecd06e04e7d3aaa76560.jpg")
LOGO_SRC = Path("/Users/lingjue/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wsywmlqy_56af/temp/RWTemp/2026-06/0d674d9d01be0014c8990f2f470dc501/a4b88b95db21909bd3e7a7a0aecfa002.jpg")
CLEAN_LOGO_SRC = Path("/Users/lingjue/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wsywmlqy_56af/temp/RWTemp/2026-06/0d674d9d01be0014c8990f2f470dc501/1ec362de5761a2db55f2e57dbc8cdd14.jpg")


def save_originals():
    robot = Image.open(ROBOT_SRC).convert("RGB")
    logo = Image.open(LOGO_SRC).convert("RGB")
    robot.save(OUT / "灵觉机器人原图.jpg", quality=95)
    logo.save(OUT / "灵觉标志原图.png")
    return robot, logo


def make_head_avatar(robot: Image.Image):
    """提取机器人头部作为头像"""
    w, h = robot.size  # 1280x1280
    # 头部在整张图的中上部，估算 ROI
    # 经观察：头顶约在 y=80，下巴约在 y=470，头宽约占 320px
    cx, cy = w // 2, 280
    size = 360
    left = cx - size // 2
    top = cy - size // 2
    right = left + size
    bottom = top + size
    head_sq = robot.crop((left, top, right, bottom))
    head_sq.save(OUT / "灵觉师兄头像_方形.jpg", quality=95)

    # 圆形头像（带透明圆角）
    head_circle = head_sq.copy()
    mask = Image.new("L", head_circle.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, head_circle.width, head_circle.height), fill=255)
    head_rgba = head_circle.convert("RGBA")
    head_rgba.putalpha(mask)
    head_rgba.save(OUT / "灵觉师兄头像_圆形.png")
    return head_sq, head_rgba

def extract_logo(logo: Image.Image):
    """把深色背景做成透明，保留圆环+文字。
    策略：先用亮度阈值+形态学+几何裁剪得到硬 mask，再叠加径向渐变做边缘羽化，
    既去掉背景与高光拖尾，又保留金属环和文字的完整质感。
    """
    rgba = logo.convert("RGBA")
    r, g, b, _ = rgba.split()
    r_arr = np.array(r)
    g_arr = np.array(g)
    b_arr = np.array(b)
    gray_arr = np.array(rgba.convert("L"))
    h, w = gray_arr.shape
    yy, xx = np.ogrid[:h, :w]

    # 1) 亮度阈值提取亮部（金属环、文字），蓝色通道保住“灵觉”
    bright = gray_arr > 120
    blue_text = (b_arr > 110) & (r_arr < 95) & (g_arr < 95)
    mask = bright | blue_text

    # 2) 形态学连接环带、文字，并裁剪掉右上角高光拖尾
    mask = ndimage.binary_dilation(mask, iterations=6)
    mask = ndimage.binary_closing(mask, iterations=8)
    mask = ndimage.binary_erosion(mask, iterations=2)

    ring_mask = ((xx - w * 0.50) ** 2 + (yy - h * 0.40) ** 2) < (min(h, w) * 0.34) ** 2
    text_mask = (xx > w * 0.28) & (xx < w * 0.72) & (yy > h * 0.62) & (yy < h * 0.80)
    mask = mask & (ring_mask | text_mask)

    # 3) 径向渐变羽化边缘（避免锯齿，并进一步压暗外围残留背景）
    dist = np.sqrt((xx - w * 0.50) ** 2 + (yy - h * 0.46) ** 2)
    max_r = min(h, w) * 0.40
    t = np.clip(dist / max_r, 0, 1)
    radial_alpha = np.clip(255 * (1 - t ** 2.0), 0, 255)

    final_alpha = (mask.astype(float) * radial_alpha)
    final_alpha = np.clip(final_alpha, 0, 255).astype(np.uint8)
    mask_img = Image.fromarray(final_alpha)
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=2))

    rgba.putalpha(mask_img)

    # 4) 提亮对比度，让金属环更亮
    enhancer = ImageEnhance.Contrast(rgba)
    rgba = enhancer.enhance(1.25)
    enhancer = ImageEnhance.Brightness(rgba)
    rgba = enhancer.enhance(1.08)

    rgba.save(OUT / "灵觉标志_透明底.png")

    # 额外输出一个“圆形徽章版”：原图裁成圆形并柔边，不做复杂抠图，最干净
    badge = logo.convert("RGBA")
    badge_mask = Image.new("L", badge.size, 0)
    draw = ImageDraw.Draw(badge_mask)
    draw.ellipse((0, 0, w, h), fill=255)
    badge_mask = badge_mask.filter(ImageFilter.GaussianBlur(radius=4))
    badge.putalpha(badge_mask)
    # 裁掉四周空白
    bbox = badge.getbbox()
    if bbox:
        badge = badge.crop(bbox)
    badge.save(OUT / "灵觉标志_圆形徽章版.png")

    return rgba


def composite_logo_on_chest(robot: Image.Image, logo_rgba: Image.Image):
    """把透明标志合成到机器人胸口"""
    robot_rgba = robot.convert("RGBA")

    # 胸口位置估算：原图 1280x1280，胸口中心约在 (640, 475)
    # 原标志 886x886，缩放到约 200x200 放在胸口
    target_size = 200
    logo_scaled = logo_rgba.resize((target_size, target_size), Image.Resampling.LANCZOS)

    cx, cy = robot_rgba.width // 2, 475
    x = cx - target_size // 2
    y = cy - target_size // 2

    # 外发光：基于标志 alpha 做一层青色光晕
    alpha = logo_scaled.split()[-1]
    glow = Image.new("RGBA", (target_size + 50, target_size + 50), (80, 180, 255, 0))
    glow_alpha = alpha.resize((target_size + 50, target_size + 50), Image.Resampling.LANCZOS)
    # 模糊光晕
    glow_alpha = glow_alpha.filter(ImageFilter.GaussianBlur(radius=12))
    glow.putalpha(ImageEnhance.Brightness(glow_alpha).enhance(0.45))
    gx = cx - glow.width // 2
    gy = cy - glow.height // 2
    robot_rgba.paste(glow, (gx, gy), glow)

    # 再贴主标志
    robot_rgba.paste(logo_scaled, (x, y), logo_scaled)

    robot_rgba.save(OUT / "灵觉机器人胸口标志版.png")
    # 同时保存一个 JPG 版兼容性更好
    robot_rgba.convert("RGB").save(OUT / "灵觉机器人胸口标志版.jpg", quality=95)
    return robot_rgba


def extract_clean_logo_with_grabcut():
    """用 OpenCV GrabCut 从白底 JPG 中抠出干净的 PROME 灵觉标志（带透明底）"""
    import cv2
    img = cv2.imread(str(CLEAN_LOGO_SRC))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]

    mask = np.zeros(img.shape[:2], np.uint8)
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    rect = (int(w * 0.15), int(h * 0.15), int(w * 0.70), int(h * 0.75))
    mask2, bgdModel, fgdModel = cv2.grabCut(
        img, mask, rect, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_RECT
    )
    alpha = np.where((mask2 == 2) | (mask2 == 0), 0, 255).astype(np.uint8)
    rgba = np.dstack((img, alpha))
    logo_clean = Image.fromarray(rgba)
    logo_clean = logo_clean.crop(logo_clean.getbbox())

    # 轻微提亮
    enhancer = ImageEnhance.Contrast(logo_clean)
    logo_clean = enhancer.enhance(1.1)
    enhancer = ImageEnhance.Brightness(logo_clean)
    logo_clean = enhancer.enhance(1.05)

    logo_clean.save(OUT / "灵觉标志_白底透明版.png")
    return logo_clean


def composite_logo_on_head_avatar(logo_rgba: Image.Image):
    """把 PROME 灵觉标志缩小后贴到师兄头像的胸口正中"""
    head = Image.open(OUT / "灵觉师兄头像_方形.jpg").convert("RGBA")

    target_w = 75
    target_h = int(logo_rgba.height * target_w / logo_rgba.width)
    logo_small = logo_rgba.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # 胸口正中位置（头像 360x360）
    cx, cy = 180, 295
    x = cx - target_w // 2
    y = cy - target_h // 2

    # 极淡光晕，让标志在黑色胸口更突出
    glow = logo_small.copy()
    glow_alpha = glow.split()[-1].filter(ImageFilter.GaussianBlur(radius=6))
    glow_alpha = glow_alpha.point(lambda p: int(p * 0.3))
    glow.putalpha(glow_alpha)
    glow = glow.resize((target_w + 12, target_h + 12), Image.Resampling.LANCZOS)
    head.paste(glow, (cx - glow.width // 2, cy - glow.height // 2), glow)

    head.paste(logo_small, (x, y), logo_small)

    head.convert("RGB").save(OUT / "灵觉师兄头像_胸口标志版.jpg", quality=95)
    head.save(OUT / "灵觉师兄头像_胸口标志版.png")
    return head


def main():
    print("开始处理灵觉/PROME 素材...")
    robot, logo = save_originals()
    print(f"原图已保存：{OUT / '灵觉机器人原图.jpg'}, {OUT / '灵觉标志原图.png'}")

    make_head_avatar(robot)
    print(f"头像已保存：{OUT / '灵觉师兄头像_方形.jpg'}, {OUT / '灵觉师兄头像_圆形.png'}")

    logo_rgba = extract_logo(logo)
    print(f"透明标志已保存：{OUT / '灵觉标志_透明底.png'}")

    composite_logo_on_chest(robot, logo_rgba)
    print(f"合成图已保存：{OUT / '灵觉机器人胸口标志版.png'}, {OUT / '灵觉机器人胸口标志版.jpg'}")

    # 用师父发来的干净白底标志，再生成头像胸口版
    if CLEAN_LOGO_SRC.exists():
        clean_logo = extract_clean_logo_with_grabcut()
        composite_logo_on_head_avatar(clean_logo)
        print(f"头像胸口版已保存：{OUT / '灵觉师兄头像_胸口标志版.jpg'}, {OUT / '灵觉师兄头像_胸口标志版.png'}")

    print("全部完成。")


if __name__ == "__main__":
    main()
