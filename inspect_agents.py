import langchain.agents
import inspect

try:
    print("Items in langchain.agents:", dir(langchain.agents))
    if hasattr(langchain.agents, 'create_agent'):
        print("\nSignature of create_agent:")
        print(inspect.signature(langchain.agents.create_agent))
    
    if hasattr(langchain.agents, 'create_react_agent'):
        print("\nFound create_react_agent")
    else:
        print("\ncreate_react_agent NOT found in langchain.agents")

except Exception as e:
    print(e)
