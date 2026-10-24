import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import render as render_mod

plan_path = sys.argv[1]
with open(plan_path, "r", encoding="utf-8") as f:
    plan = json.load(f)

ru_path = render_mod.generate_title_image(
    plan, "Путешествие вокруг Земли за 185 дней",
    title_subtitle="2018 — 2019", kicker="Кругосветное путешествие",
    output_path=os.path.join(render_mod.OUTPUT_DIR, f"{plan['job_id']}_title_ru.png"),
)
en_path = render_mod.generate_title_image(
    plan, "Around the World in 185 Days",
    title_subtitle="2018 — 2019", kicker="World Trip",
    output_path=os.path.join(render_mod.OUTPUT_DIR, f"{plan['job_id']}_title_en.png"),
)
print("RU:", ru_path)
print("EN:", en_path)
