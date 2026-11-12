TOPICS = [
    {
        "id": "study", "name": "Study & work", "icon": "graduation-cap",
        "questions": [
            "Do you work or are you a student?",
            "What do you enjoy most about your studies or your work?",
            "What is a typical weekday like for you?",
            "Do you prefer working alone or with other people?",
            "What would you like to do after you finish your studies or your current job?",
        ],
    },
    {
        "id": "home", "name": "Home & hometown", "icon": "house",
        "questions": [
            "Can you tell me about the place where you live?",
            "What do you like most about your hometown?",
            "Is there anything you would like to change about your neighborhood?",
            "Which room do you spend the most time in at home?",
            "Would you like to live in the same place in the future?",
        ],
    },
    {
        "id": "leisure", "name": "Free time", "icon": "headphones",
        "questions": [
            "What do you usually do in your free time?",
            "Do you prefer spending your free time indoors or outdoors?",
            "What kind of music do you enjoy listening to?",
            "Have your hobbies changed since you were a child?",
            "Is there a new activity you would like to try?",
        ],
    },
]


def question_bank():
    return [{**topic, "questions": [
        {"id": f"{topic['id']}-{index + 1}", "text": text}
        for index, text in enumerate(topic["questions"])
    ]} for topic in TOPICS]


QUESTIONS = {
    question["id"]: question
    for topic in question_bank() for question in topic["questions"]
}

PREPARATION_SECONDS = 60
PART2_SPEAKING_SECONDS = 120
CUE_CARDS = [
    {
        "id": "part2-skill", "part": 2, "title": "A useful skill",
        "text": "Describe a skill you learned that is useful to you.",
        "points": ["what the skill is", "when and how you learned it", "how you use it now"],
        "explain": "and explain why this skill is important to you.",
    },
    {
        "id": "part2-place", "part": 2, "title": "A place to return to",
        "text": "Describe a place you have visited and would like to visit again.",
        "points": ["where the place is", "when you went there", "what you did there"],
        "explain": "and explain why you would like to return to this place.",
    },
    {
        "id": "part2-person", "part": 2, "title": "Someone who helped you",
        "text": "Describe a person who helped you with something difficult.",
        "points": ["who the person is", "what you needed help with", "how the person helped you"],
        "explain": "and explain how you felt about receiving their help.",
    },
    {
        "id": "part2-object", "part": 2, "title": "An everyday object",
        "text": "Describe an object you use often in your daily life.",
        "points": ["what the object is", "how you got it", "when and how you use it"],
        "explain": "and explain how your daily life would be different without it.",
    },
    {
        "id": "part2-project", "part": 2, "title": "A project with others",
        "text": "Describe a project you worked on with other people.",
        "points": ["what the project was", "who you worked with", "what your role was"],
        "explain": "and explain what you learned from working on this project.",
    },
    {
        "id": "part2-activity", "part": 2, "title": "An activity to try",
        "text": "Describe an activity you would like to try in the future.",
        "points": ["what the activity is", "where you would do it", "who you would like to do it with"],
        "explain": "and explain why you are interested in trying this activity.",
    },
]
QUESTIONS.update({card["id"]: card for card in CUE_CARDS})
