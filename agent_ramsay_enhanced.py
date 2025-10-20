# Enhanced KitchenCompanion Agent with Authentic Gordon Ramsay Personality
import asyncio
import random
from typing import Optional

from livekit.agents import Agent, ChatContext, ChatMessage
from livekit.agents import function_tool, RunContext

# Import the enhanced persona functions
from agent_enhanced import (
    ramsay_persona_enhanced, 
    get_ramsay_greeting, 
    get_ramsay_encouragement, 
    get_ramsay_correction
)

class RamsayKitchenCompanionAgent(Agent):
    """Enhanced AI Chef agent with authentic Gordon Ramsay personality and teaching style."""

    def __init__(self, chat_ctx: ChatContext = None, spice_level: str = "pg13"):
        super().__init__(
            chat_ctx=chat_ctx or ChatContext(),
            instructions=ramsay_persona_enhanced(spice_level),
        )
        self.spice_level = spice_level
        self.user_name = None
        self.cooking_experience = "beginner"  # Track user's cooking level

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        """
        Enhanced user interaction with Ramsay's personality traits.
        """
        user_text = new_message.text_content() or ""
        
        # Detect cooking experience level
        self._detect_cooking_experience(user_text)
        
        # Check for cooking mistakes or poor practices
        if self._detect_cooking_mistakes(user_text):
            correction = get_ramsay_correction()
            turn_ctx.add_message(
                role="assistant",
                content=f"{correction} {self._get_mistake_explanation(user_text)}"
            )
            return
        
        # Check for good practices
        if self._detect_good_practices(user_text):
            encouragement = get_ramsay_encouragement()
            turn_ctx.add_message(
                role="assistant",
                content=f"{encouragement} {self._get_encouragement_details(user_text)}"
            )
            return
        
        # Perform RAG lookup for cooking questions
        cooking_keywords = [
            "cook", "recipe", "ingredient", "salt", "fat", "acid", "heat",
            "temperature", "bake", "boil", "fry", "roast", "season", "technique",
            "flavor", "texture", "prepare", "dish", "meal", "food", "taste",
            "spice", "herb", "sauce", "vegetable", "meat", "fish", "pasta",
            "rice", "bread", "knife", "cut", "chop", "blend", "mix", "stir",
            "sear", "caramelize", "deglaze", "rest", "marinate", "brine"
        ]
        
        is_cooking_query = any(k in user_text.lower() for k in cooking_keywords)

        if is_cooking_query and len(user_text) > 10:
            print(f"🔍 RAG Lookup: {user_text[:100]}...")
            cookbook_knowledge = await asyncio.to_thread(query_cookbook, user_text)

            if cookbook_knowledge and "don't have access" not in cookbook_knowledge.lower():
                # Inject as Chef's Notes with Ramsay's style
                ramsay_intro = self._get_ramsay_cookbook_intro()
                turn_ctx.add_message(
                    role="assistant",
                    content=(
                        f"{ramsay_intro}\n\n"
                        f"**Chef's Notes (from my cookbook):**\n{cookbook_knowledge}\n\n"
                        f"{self._get_ramsay_instruction_style()}"
                    ),
                )
                print("✅ Added cookbook context with Ramsay personality")
            else:
                print("⚠️  No relevant cookbook knowledge found")

    def _detect_cooking_experience(self, user_text: str):
        """Detect user's cooking experience level."""
        beginner_indicators = ["first time", "never cooked", "beginner", "don't know how", "new to cooking"]
        intermediate_indicators = ["sometimes cook", "basic cooking", "home cook"]
        advanced_indicators = ["professional", "chef", "restaurant", "advanced"]
        
        text_lower = user_text.lower()
        
        if any(indicator in text_lower for indicator in beginner_indicators):
            self.cooking_experience = "beginner"
        elif any(indicator in text_lower for indicator in advanced_indicators):
            self.cooking_experience = "advanced"
        elif any(indicator in text_lower for indicator in intermediate_indicators):
            self.cooking_experience = "intermediate"

    def _detect_cooking_mistakes(self, user_text: str) -> bool:
        """Detect cooking mistakes or poor practices."""
        mistake_indicators = [
            "undercooked", "raw", "cold", "frozen", "not seasoned", "no salt",
            "burnt", "overcooked", "dry", "tough", "rubber", "soggy",
            "cross contamination", "same cutting board", "not washed",
            "left out", "room temperature meat", "expired", "smells bad"
        ]
        return any(mistake in user_text.lower() for mistake in mistake_indicators)

    def _detect_good_practices(self, user_text: str) -> bool:
        """Detect good cooking practices."""
        good_indicators = [
            "seasoned properly", "rested the meat", "preheated", "sharp knife",
            "fresh ingredients", "proper temperature", "tasted", "beautiful",
            "perfect", "delicious", "tender", "juicy", "crispy", "golden"
        ]
        return any(good in user_text.lower() for good in good_indicators)

    def _get_mistake_explanation(self, user_text: str) -> str:
        """Get Ramsay-style explanation for cooking mistakes."""
        if "undercooked" in user_text.lower() or "raw" in user_text.lower():
            return "That's DANGEROUS! You'll make someone sick! Always cook meat to the proper internal temperature!"
        elif "not seasoned" in user_text.lower() or "no salt" in user_text.lower():
            return "Where's the FLAVOR?! Season as you go! Salt is your best friend in the kitchen!"
        elif "burnt" in user_text.lower() or "overcooked" in user_text.lower():
            return "That's drier than the Sahara! Watch your heat and timing!"
        elif "cross contamination" in user_text.lower():
            return "That's how you poison people! Use separate cutting boards for meat and vegetables!"
        else:
            return "That's not how you do it! Let me show you the proper technique!"

    def _get_encouragement_details(self, user_text: str) -> str:
        """Get Ramsay-style encouragement details."""
        if "seasoned properly" in user_text.lower():
            return "Seasoning is everything! You're getting the fundamentals right!"
        elif "rested the meat" in user_text.lower():
            return "Perfect! Resting is crucial for tender, juicy meat!"
        elif "fresh ingredients" in user_text.lower():
            return "Quality ingredients make all the difference! You understand that!"
        elif "tasted" in user_text.lower():
            return "Always taste! That's how you develop your palate!"
        else:
            return "You're cooking with passion! That's what it's all about!"

    def _get_ramsay_cookbook_intro(self) -> str:
        """Get Ramsay-style introduction to cookbook knowledge."""
        intros = [
            "Right! Let me pull something from my cookbook for you...",
            "Perfect question! I've got just the thing in my cookbook...",
            "Excellent! Let me check my cookbook for the proper technique...",
            "Right! I know exactly what you need from my cookbook...",
            "Brilliant question! Let me get the details from my cookbook..."
        ]
        return random.choice(intros)

    def _get_ramsay_instruction_style(self) -> str:
        """Get Ramsay-style instruction conclusion."""
        conclusions = [
            "Right! Now let's nail this—step by step, with passion!",
            "Perfect! Now follow these steps and cook with confidence!",
            "Excellent! Now execute this with precision and love!",
            "Right! Now let's cook this properly—technique first!",
            "Brilliant! Now let's make this BEAUTIFUL!"
        ]
        return random.choice(conclusions)

    async def get_ramsay_greeting(self) -> str:
        """Get a personalized Ramsay greeting."""
        greeting = get_ramsay_greeting()
        if self.cooking_experience == "beginner":
            greeting += " Don't worry, I'll teach you everything you need to know!"
        elif self.cooking_experience == "advanced":
            greeting += " I can see you know your way around a kitchen!"
        return greeting

# Enhanced function tools with Ramsay personality
@function_tool()
async def ramsay_convert_units(amount: float, from_unit: str, to_unit: str):
    """Convert between common kitchen units with Ramsay's precision."""
    conversions = {
        ("cup", "tbsp"): 16, ("tbsp", "tsp"): 3, ("cup", "ml"): 240,
        ("tbsp", "ml"): 15, ("tsp", "ml"): 5, ("cup", "g"): 200,
        ("tbsp", "g"): 12.5, ("tsp", "g"): 4.2,
    }

    fu, tu = from_unit.strip().lower(), to_unit.strip().lower()
    factor = conversions.get((fu, tu))
    if not factor:
        reverse_factor = conversions.get((tu, fu))
        if reverse_factor:
            factor = 1 / reverse_factor

    if not factor:
        return f"Right! I'm not sure how to convert {from_unit} to {to_unit}. Let me think about this..."

    result = amount * factor
    return f"Perfect! {amount} {from_unit} = **{result:.2f} {to_unit}**. Now get measuring with PRECISION!"

@function_tool()
async def ramsay_find_grocery_stores(city: str):
    """Find grocery stores with Ramsay's emphasis on quality ingredients."""
    # This would integrate with your existing grocery store finder
    # but with Ramsay's personality
    return f"Right! Let me find you the best grocery stores in {city}. Quality ingredients make ALL the difference!"

