import httpx

# available backends (top is default)
available_backends=[
    ## GPT models ##
    "gpt-4o",
    "gpt-4o-mini",
    "o3-mini",
    # "o1-mini",
    ## Ollama models ##
    #"llama3.2:3B",
    "qwen2.5:3b",
    "deepseek-r1:32b"
]