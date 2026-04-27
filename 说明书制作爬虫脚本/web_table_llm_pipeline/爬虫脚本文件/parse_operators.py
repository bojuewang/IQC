import re
import pandas as pd

with open("operators_page_text.txt", "r", encoding="utf-8") as f:
    text = f.read()

# 去掉页面噪音（顶部菜单等）
start = text.find("Arithmetic")
text = text[start:]

# 按 operator 切分（核心）
pattern = r"\n([a-zA-Z_]+\([^\n]*\))\n"

splits = re.split(pattern, text)

data = []

for i in range(1, len(splits), 2):
    operator = splits[i].strip()
    block = splits[i + 1]

    lines = block.strip().split("\n")

    level = lines[0] if len(lines) > 0 else ""
    short_desc = lines[1] if len(lines) > 1 else ""

    # long desc
    long_desc = ""
    examples = ""

    if "Examples:" in block:
        parts = block.split("Examples:")
        long_desc = parts[0].replace("Show less", "").strip()
        examples = parts[1].strip()
    else:
        long_desc = block.replace("Show less", "").strip()

    data.append({
        "operator": operator,
        "level": level,
        "short_desc": short_desc,
        "long_desc": long_desc,
        "examples": examples
    })

df = pd.DataFrame(data)

df.to_csv("operators_full.csv", index=False, encoding="utf-8-sig")

print("✅ Done:", len(df))
print(df.head())
