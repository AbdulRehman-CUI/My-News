"""The single source of truth for onboarding choices, including all subtopics."""

TOPICS = {
    "Technology": ["AI", "Software", "Gadgets", "Robotics"],
    "Science": ["Space", "Physics", "Biology", "Research"],
    "Business": ["Startups", "Markets", "Economy", "Work"],
    "Sports": ["Cricket", "Football", "Tennis", "Athletics"],
    "Entertainment": ["Film", "Music", "Television", "Performing arts"],
    "Politics": ["Elections", "Public policy", "International relations", "Local government"],
    "Health": ["Public health", "Medicine", "Wellbeing", "Nutrition"],
    "Education": ["Schools", "Universities", "Learning", "Education policy"],
    "Environment": ["Climate", "Conservation", "Clean energy", "Oceans"],
    "Culture": ["Art", "Books", "History", "Heritage"],
    "Travel": ["Destinations", "Rail travel", "Local experiences", "Sustainable travel"],
    "Gaming": ["PC gaming", "Console gaming", "Indie games", "Esports"],
}
AGES = ["Under 18", "18–29", "30–49", "50+"]
EDUCATION = ["School", "College", "Undergraduate", "Postgraduate", "Other", "Prefer not to say"]
ACTIVITIES = ["Studying", "Employed", "Freelancing", "Business owner", "Job seeking", "Retired", "Other"]
REGIONS = ["Worldwide", "Pakistan", "India", "Bangladesh", "China", "Japan", "Middle East", "Africa", "Europe", "United Kingdom", "United States", "Canada", "Latin America", "Australia & New Zealand"]
STEPS = [
    ("age", "A little context", "Age range is optional. It will not determine your interests or expertise."),
    ("education", "Your education", "Optional context, never a shortcut to assumptions about what you know."),
    ("activities", "What keeps you busy?", "Choose any that fit your life right now, or skip."),
    ("interests", "Make room for your interests", "Pick the subjects you would like to see in your paper."),
    ("subtopics", "Go a little deeper", "Explore the subjects within your interests. Choose as many as you like."),
    ("regions", "Your window on the world", "Choose places you care about. Coverage will depend on future sources."),
    ("calibration", "What would you open?", "Choose examples that catch your attention, or skip. These are fictional setup examples, not current reporting."),
    ("morning", "Give your morning a head start", "Confirm your timezone and preferred ready time. Automatic delivery comes in a later phase."),
]
