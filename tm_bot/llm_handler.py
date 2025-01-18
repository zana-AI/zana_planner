import os
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LLMHandler:
    def __init__(self):
        # Fetch the OpenAI API key from environment variables
        self.openai_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_key:
            raise ValueError("OpenAI API key is not set in environment variables.")
        
        # Initialize the LangChain OpenAI Chat Model
        self.chat_model = ChatOpenAI(
            openai_api_key=self.openai_key,
            temperature=0.7,  # Adjust based on your use case
            model="gpt-4"  # Specify the model (gpt-3.5-turbo, gpt-4, etc.)
        )
        print("LLMHandler initialized successfully")

    def get_response(self, user_message: str) -> str:
        """
        Sends a message to the LLM and retrieves the response.
        """
        try:
            # Send the user's message to the LLM and get a response
            response = self.chat_model([HumanMessage(content=user_message)])
            return response.content
        except Exception as e:
            return f"An error occurred while processing your request: {e}"
