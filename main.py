# 
from dotenv import load_dotenv
import os

from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate

# Load env
load_dotenv()

# LLM (Groq)
llm = ChatOpenAI(
    model="openai/gpt-oss-120b",
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# Prompt (IMPORTANT: includes agent_scratchpad)
prompt = ChatPromptTemplate.from_messages([
    ("system",
     
     "You are an AI agent. "
     "Answer in very simple English. "
     "One line only. "
     "perfrom addication take input from the user "
     "If you do not know, say: I don't know. "
     "If question is about weather, use the tool."),
     
     
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}")
])

# Tool
@tool
def get_temperature(city: str) -> str:
    """Returns temperature of a city."""
    data = {
        "delhi": "35°C",
        "mumbai": "30°C",
        "bangalore": "28°C"
    }
    return f"The temperature in {city.title()} is {data.get(city.lower(), 'unknown')}"
@tool
def addtication(a,b):
    """retrun the sum"""
    sum=a+b

tools = [get_temperature,addtication]


# Agent
agent = create_openai_tools_agent(
    llm=llm,
    tools=tools,
    prompt=prompt
)

# AgentExecutor 
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True
)

# Chat loop
while True:
    text = input("You: ")
    if text.lower() == "exit":
        break

    result = agent_executor.invoke({"input": text})
    print("AI:", result["output"])
    print("-" * 40)
