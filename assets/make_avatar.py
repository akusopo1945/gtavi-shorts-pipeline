from PIL import Image, ImageDraw, ImageFont
import math

SIZE = 512
im = Image.new('RGB', (SIZE, SIZE), color=(11, 15, 25))
draw = ImageDraw.Draw(im)

# Gradient / glow background circle
for r in range(250, 160, -2):
    alpha = int(120 * (1 - (r - 160) / 90))
    col = (236, 72, 153) if r % 4 == 0 else (6, 182, 212)
    # subtle circle
    draw.ellipse([256 - r, 256 - r, 256 + r, 256 + r], outline=col + (alpha,) if len(col) == 4 else col, width=1)

# Solid dark inner circle
draw.ellipse([56, 56, 456, 456], fill=(15, 23, 42), outline=(236, 72, 153), width=5)
draw.ellipse([64, 64, 448, 448], outline=(6, 182, 212), width=3)

# Load font
try:
    font_large = ImageFont.truetype('/data/gtavi-claudecode/assets/fonts/BebasNeue-Bold.otf', 110)
    font_sub = ImageFont.truetype('/data/gtavi-claudecode/assets/fonts/Montserrat-Bold.otf', 26)
    font_tag = ImageFont.truetype('/data/gtavi-claudecode/assets/fonts/Montserrat-ExtraBold.otf', 18)
except:
    font_large = font_sub = font_tag = ImageFont.load_default()

# Clapper / Play Icon at top
draw.polygon([(230, 140), (290, 175), (230, 210)], fill=(6, 182, 212))
draw.ellipse([210, 130, 310, 220], outline=(236, 72, 153), width=3)

# Text: LUNA
draw.text((256, 275), "LUNA", fill=(255, 255, 255), font=font_large, anchor="mm")

# Glow line divider
draw.line([(140, 340), (372, 340)], fill=(6, 182, 212), width=3)

# Subtitle: AUTO CLIPPER
draw.text((256, 375), "AI CLIPPER", fill=(236, 72, 153), font=font_sub, anchor="mm")
draw.text((256, 410), "GTA VI SHORTS ENGINE", fill=(148, 163, 184), font=font_tag, anchor="mm")

avatar_path = '/data/gtavi-claudecode/assets/bot_avatar.png'
im.save(avatar_path, 'PNG')
print(f"Avatar generated at {avatar_path}")
