from router import ModelRouter


router = ModelRouter()

answer = router.complete(
    role="coder",
    messages=[
        {
            "role": "user",
            "content": (
                "Reply with exactly: "
                "LOCAL ORCHESTRATOR WORKING"
            ),
        }
    ],
)

print(answer)
