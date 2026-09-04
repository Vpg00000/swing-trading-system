from router import ModelRouter


router = ModelRouter()

print("MODEL ROUTER")
print("=" * 70)

for item in router.status():
    print(
        f"{item['id']:<25} "
        f"priority={item['priority']:<3} "
        f"roles={','.join(item['roles'])} "
        f"healthy={item['healthy']} "
        f"free={item['free']} "
        f"local={item['local']}"
    )

print()
print("Planner candidates:")

for model in router.select_all("planner"):
    print(
        f"  {model['id']} "
        f"-> {model['model']}"
    )

print()
print("Coder candidates:")

for model in router.select_all("coder"):
    print(
        f"  {model['id']} "
        f"-> {model['model']}"
    )