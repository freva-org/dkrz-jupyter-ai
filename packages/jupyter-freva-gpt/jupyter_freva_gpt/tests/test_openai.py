import openai
client = openai.OpenAI()

completion=openai.chat.completions.create(
    model= "gpt-4o-mini",
    messages= [
        {"role": "user", "content": "Create some python code to plot a sine curve between 0 and 1"}
    ]
)
print(completion.choices)
print(completion.choices[0].message)