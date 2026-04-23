import os
import glob

old = "watsonx/ibm/granite-3-3-8b-instruct"
new = "watsonx/ibm/granite-3-8b-instruct"

files = glob.glob("agents/*.yaml")
for f in files:
    with open(f, "r", encoding="utf-8") as file:
        content = file.read()
    if old in content:
        content = content.replace(old, new)
        with open(f, "w", encoding="utf-8") as file:
            file.write(content)
        print(f"Corrigido: {f}")
    else:
        print(f"OK (sem alteracao): {f}")

print("Concluido!")