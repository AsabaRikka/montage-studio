"""Reproduce the original Montage Studio splice/play brand and Windows icon."""
from pathlib import Path
from PIL import Image, ImageDraw

folder = Path(__file__).resolve().parent.parent / 'assets/ui'
folder.mkdir(parents=True, exist_ok=True)
image = Image.new('RGBA', (1024, 1024))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((32, 32, 992, 992), radius=230, fill='#242424')
# Two strips brought together around a forward/play cut, not a third-party mark.
draw.polygon([(236, 272), (438, 272), (536, 512), (438, 752), (236, 752), (334, 512)], fill='#fafafa')
draw.polygon([(550, 272), (754, 272), (852, 512), (754, 752), (550, 752), (648, 512)], fill='#fafafa')
image.resize((512, 512), Image.Resampling.LANCZOS).save(folder / 'logo.png')
image.save(folder / 'MontageStudio.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(folder)
