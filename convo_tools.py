from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.prompts import PromptTemplate, SystemMessagePromptTemplate
from langchain.memory import ChatMessageHistory
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_core.pydantic_v1 import BaseModel, Field, validator
from deepgram import DeepgramClient, SpeakOptions
import time
import os

# some global variables
# fudging a database of memories about teachers
# production version would pull from a database
# other fields for memory: fun facts, demographics, past performance, etc.

all_memories = {
    "agasthya":
        {
            'summary': "Agasthya is a first year teacher teaching freshman algebra. he's got the math down but is struggling with classroom management.",
            'coach_notes': ["2024-05-14: observed agasthya's 1st period class. kids were rowdy. low engagement during intro to systems of equations - students seemed lost. very important - need clearer explanation for tomorrows class (important for reteach).",
                         "2024-05-07: had a coaching convo, focused on analyzing student work. at end of session, seems clear that agas knows the math well."],
            'nisa_memories': ["I have never met Agasthya before. He is new to the platform."]
            },
    "adam":
        {
            'summary': "Adam is a 3rd year teacher teaching AP US History. he is stressed about keeping up the pace to be ready for the AP exam.",
            'coach_notes': ["2024-05-14: observed adam's 8th period class. half the kids were disengaged (after lunch, tired). lingered for too long on tangent about eminent domain. how to practice noticing when he himself is off track?",
                         "2024-05-07: did some lesson co-planning. we agreed that I'll focus in on his questioning strategy in my next obs."],
            'nisa_memories': ["2024-05-07: this was my first session with Adam. It's his first year teaching APUS and noted that the DBQs are really giving his kids trouble."]
            },
    "merlin":
        {
            'summary': "Merlin is a 5th year teacher teaching 10th grade english. He's interested in different lesson models like inquiry-based teaching.",
            'coach_notes': ["2024-05-14: observed merlin's 3rd period class. kids were quitely working. asked one student to explain the assignment and he did so clearly.",
                         "2024-05-07: had a coaching convo about planning for final novel. thinking of some ways to make the text come alive instead of standard close reading."],
            'nisa_memories': ["2024-05-07: this was my first session with Merlin. He told me that he's really into anime and wants to take his students to Japan one day."]
            },
    "vaish": 
        {
            'summary': "Vaish is a 2nd year teacher teaching 10th grade chemistry. she's struggling with keeping her students engaged.",
            'coach_notes': ["2024-05-14: observed vaish's 5th period class. kids were engaged in the lab. vaish was able to keep them on task and focused.",
                            "2024-05-07: had a coaching convo about the upcoming unit on chemical reactions. vaish is worried about the labs."],
            'nisa_memories': ["2024-05-07: this was my first session with Vaish. She told me she's a big fan of the periodic table song."]
            },
    "gautam":
        {
            'summary': "Gautam is a 4th year teacher teaching 9th grade ELA. He wants to get better at giving the highest leverage feedback on student writing.",
            'coach_notes': ["2024-05-14: observed gautam's 2nd period class. kids were working on essays. gautam tried to give individual feedback to each student as he circulated but ran out of time. need to practice prioritizing feedback.",
                            "2024-05-07: had a coaching convo about the upcoming essay unit. talked about how G will follow up with students re: incorporating feedback."],
            'nisa_memories': ["2024-05-07: this was my first session with Gautam. He told me he's a Stanford alum and is a big fan of their sports teams, especially basketball."]
        },
    "abhi":
        {
            'summary': "Abhi is a 6th year teacher teaching 11th grade physics. He's interested in incorporating more hands-on labs into his curriculum.",
            'coach_notes': ["2024-05-14: observed abhi's 4th period class. kids were working on worksheets. quiet but focused, abhi was circulating. focus: how to get kids to talk more about their thinking.",
                            "2024-05-07: had a coaching convo about the upcoming unit on electricity. abhi is worried about the labs."],
            'nisa_memories': ["2024-05-07: this was my second session with Abhi. We tal ked about how he feels like the AP Physics teacher gets more support than him"]
            
        },
    "sarah":
        {
            'summary': "Sarah is a 3rd year teacher teaching 12th grade English. She's interested in incorporating more student-led discussions into her curriculum.",
            'coach_notes': ["2024-05-14: observed sarah's 6th period class. kids were working on group projects. sarah was circulating and giving feedback. focus: how to get kids to talk more about their thinking.",
                            "2024-05-07: had a coaching convo about the upcoming unit on poetry. sarah is worried about the discussions re: kids taking it seriously (some of the poems have adult themes)."],
            'nisa_memories': ["2024-05-07: this was my second session with Sarah. We talked about how the standard canon doesn't have enough authors of color."]
        },
}

def initialize_chain(model_shorthand,system_prompt, history=False):

    output_parser = StrOutputParser()
    
    model_name = {
        'gpt':'gpt-4o-2024-05-13',
        'llama':'llama3-70b-8192',
        'haiku':'claude-3-haiku-20240307'
    }

    name = model_name[model_shorthand]

    model_farm = {
        'gpt':ChatOpenAI,
        'llama':ChatGroq,
        'haiku':ChatAnthropic
    }

    model = model_farm[model_shorthand](model=name)

    if history:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    system_prompt,
                ),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human","{input}"),
            ]
        )
        base_chain = prompt | model | output_parser
        message_history = ChatMessageHistory()
        chain = RunnableWithMessageHistory(
            base_chain,
            lambda session_id: message_history,
            input_messages_key="input",
            history_messages_key="chat_history",
        )

    else:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    system_prompt
                ),
                (
                    "human",
                    "{input}"
                )
            ]
        )
        chain = prompt | model | output_parser

    return chain

# runs one turn of a conversation
def conversation_engine(chain, input):
    message = chain.invoke({"input":input},
                        {"configurable": {"session_id": "unused"}})
    return message

def extract_practice_scenario(memories, coach_notes):
    scenario_maker_prompt = """
    You look at a coach's notes and extract the practice scenario that the coach wants the teacher to practice. 
    Sometimes the coach's notes will not have an explicit practice focus. in that case, use the coach's notes along with memories about the user to determine the appropriate practice scenario.
    Your only output should be the practice scenario, along with your reasoning for choosing.
    ---
    example 1:
    coach_notes: "2024-05-14: observed agasthya's 1st period class. kids were rowdy. need to focus on transitioning from Do Now to INM smoothly and without losing control."
    memories_about_user: "Agasthya is a first year teacher teaching freshman algebra. he's got the math down but is struggling with classroom management."
    output: "Transition from Do Now to INM. Reasoning: coach indication."

    example 2:
    coach_notes: "2024-05-14: observed adam's 8th period class. half the kids were disengaged (after lunch, tired). lingered for too long on tangent about eminent domain. how to practice noticing when he himself is off track?"
    memories_about_user: "Adam is a 3rd year teacher teaching AP US History. he is stressed about keeping up the pace to be ready for the AP exam."
    output: "Script high-leverage student questions for discussion. Reasoning: scripted questions will keep Adam on track."

    example 3:
    coach_notes: "2024-05-14: observed sarah's 3rd period class. kids were quitely working. asked one student to explain the assignment and they did so clearly."
    memories_about_user: "Sarah is a 5th year teacher teaching 10th grade english. she's interested in different lesson models like inquiry-based teaching."
    output: "Plan a socratic seminar. Reasoning: Sarah is interested in inquiry-based teaching."
    """
    scenario_maker = initialize_chain("llama",scenario_maker_prompt)
    scenario = scenario_maker.invoke({"input":f"coach_notes: {coach_notes} \n memories_about_user: {memories}"})
    return scenario

def create_look_fors(scenario):
    look_for_system_prompt = """
    You are a seasoned instructional coach with deep experience in classroom observation and pedagogical best practices. your main focus is to take practice scenarios and infer or extract the "look-fors", that are indicative of exemplary work. 

    EXAMPLE 1:
    scenario: explain the difference between similes and metaphors.

    look-fors:
    - Teacher uses the terms 'literary device', 'figurative language'
    - Teacher gives an example of a simile and an example of a metaphor
    - Teacher emphasizes that a metaphor can be more than just a sentence, it can be an entire work

    EXAMPLE 2:
    scenario: give directions for transitioning from group work to independent practice.

    look-fors:
    - Teacher uses attention-getting strategy
    - Teacher uses phrase "when I say go"
    - Teacher gives no more than 3 instructions at a time

    It is important that your look-fors do not include visuals: someone reading the transcript of the practice should be able to determine the presence of any look-for. Create no more than 4 look-fors per scenario. Be sure that your look-fors meet the non-visual criteria.
    """

    lookforbot = initialize_chain("llama",look_for_system_prompt)
    print("initialized lookforbot, invoking...")
    look_fors = lookforbot.invoke({"input":scenario})
    return look_fors

def create_thinking_plan(scenario, look_fors):
    planning_system_prompt = """
    You are a seasoned instructional coach with deep experience in classroom observation and pedagogical best practices. 
    your main focus is to take practice scenarios along with their look-fors and create a thinking guide for coaches to use while facilitating practice with teachers. 

    EXAMPLE 1:
    scenario: explain the difference between similes and metaphors.
    look-fors:
    - Teacher uses the terms 'literary device', 'figurative language'
    - Teacher gives an example of a simile and an example of a metaphor
    - Teacher emphasizes that a metaphor can be more than just a sentence, it can be an entire work

    thinking guide:
    I need to make sure I see evidence of the teacher using the terms 'literary device' and 'figurative language'. 
    I also need to see the teacher give an example of a simile and an example of a metaphor. 
    Finally, I need to see the teacher emphasize that a metaphor can be more than just a sentence, it can be an entire work. 

    I also need to make sure that I'm steering them towards achieving the look-fors without being too prescriptive.

    So: 
    - if I notice the teacher using non-academic terms, like "a simile is a kind of way to show how two things are alike", I might ask them to rephrase it in more academic terms on their next round.
    - if I notice that the teacher gives an example of only one type of figurative language, I might ask them to give an example of the other type on their next round.
    - I think it's possible that the teacher will struggle to explain how a metaphor can be an entire work. If that happens, I might give an example of what it means, and ask them to come up with their own example on their next round.
    - I think it's possible that the teacher will want to explain the concepts in a fun way. If that happens, I'll praise their creativity and remind them to incorporate the academic terms as well.

    EXAMPLE 2:
    scenario: give directions for transitioning from group work to independent practice.
    look-fors:
    - Teacher uses attention-getting strategy
    - Teacher uses phrase "when I say go"
    - Teacher gives no more than 3 instructions at a time

    thinking guide:
    I need to make sure I see evidence of the teacher using an attention-getting strategy.
    I also need to see the teacher use the phrase "when I say go". 
    Finally, I need to see the teacher give no more than 3 instructions at a time.

    I also need to make sure that I'm steering them towards achieving the look-fors without being too prescriptive.

    So:
    - if I notice the teacher doesn't use an attention-getting strategy, I might suggest they try using one on their next round.
    - if I notice the teacher gives more than 3 instructions at a time, I might suggest they try giving fewer instructions on their next round.
    - I think it's possible that the teacher will get the order of their instructions mixed up. If that happens, I might suggest breaking the instructions up even more.
    - I think it's possible that the teacher will forget to use the phrase "when I say go". If that happens, I might suggest they try using it on their next round.
    """

    plannerbot = initialize_chain("llama",planning_system_prompt)
    print("initialized plannerbot, invoking...")
    thinking_plan = plannerbot.invoke({"input":scenario + "\n" + look_fors})
    return thinking_plan

def get_practice_context(memories, coach_notes):
    practice_scenario = extract_practice_scenario(memories, coach_notes)
    print(f"practice scenario: {practice_scenario}")
    print("generating look fors for practice scenario")
    look_fors = create_look_fors(practice_scenario)
    print("generating thinking plan")
    thinking_plan = create_thinking_plan(practice_scenario,look_fors)
    return {
        "scenario":practice_scenario,
        "look_fors":look_fors,
        "thinking_plan":thinking_plan
    }

def get_memories(user):
    global all_memories
    user_memories = all_memories[user]
    memories = f"summary for {user}: {user_memories['summary']}\n nisa's memories: {user_memories['nisa_memories']}"
    coach_notes = user_memories['coach_notes']
    return memories, coach_notes

def make_memories(user, transcript):
    global all_memories
    today = time.strftime("%Y-%m-%d")

    # haha get it like in The Giver
    reciever = initialize_chain("llama", 
                                """
                                you review transcripts as input and output any important information that should be remembered about the user.
                                things that should be remembered include:
                                - fun facts
                                - performance, goals, etc
                                - personal preferences
                                ---
                                output all memories in a single string separated by commas with today's date as the prefix (year-month-day).
                                Example:
                                2022-03-15: Agasthya is worried about teaching 6th grade math, Agasthya practiced explaining ratios but struggled with the concept, Agasthya is going to try to use more visual aids in the future.
                                ---
                                today's date: {}
                                """.format(today)
                                )
    
    memory = reciever.invoke({"input":transcript})
    all_memories[user]['nisa_memories'].append(memory)
    return all_memories

def create_coach_with_context(model_shorthand, user, memories_about_user, coach_notes, practice_context):
    # memories_about_user, coach_notes = get_memories(user)
    # practice_context = get_practice_context(memories_about_user, coach_notes[0])
    coach_sys_prompt = """
    You are Nisa, a seasoned instructional coach with deep experience in classroom observation and pedagogical best practices. 
    You are guiding a teacher through a practice scenario. the practice scenario has been decided by the user's human coach.
    You are the human coach's AI counterpart. The teacher you are interacting with knows you are an AI. Only remind them that you are an AI if absolutely necessary.
    You will begin the session by asking the teacher how they are. You will not overload them with context for the session.
    Instead, you will engage in a short, normal candence conversation with them to start.

    IMPORTANT: in order for the user experience to be smooth, you should keep your responses short, like a real human would in a live conversation. A good heuristic is to keep your responses to 1-2 sentences, unless the user explicitly asks for more information or a more in-depth answer.
    It is essential you stick to this heuristic to ensure the user has a good experience and the conversation flows smoothly.
    The better you are at following these instructions, the better experience the teacher will have, and you will have a positive impact on the children they teach.
    If you do not follow these instructions, you can have a negative impact on the teacher and the children they teach.

    YOU MUST FOLLOW THE JSON FORMATTING INSTRUCTIONS. FAILURE TO DO SO WILL BREAK THE SYSTEM AND CAUSE A CRASH.

    Example (in this example, assume all coach responses are formatted as valid JSON, even if not directly reflected.):
    user: begin session. do not acknowledge reciept of this message.
    coach: "message": "hey [user], how are you today? Your coach told me about their observation, and we've put together a quick practice session for you. Sound good?", "action": "listen to user"
    user: um oh hey yeah I'm good. cool.
    coach: "message":"great! [appropriate follow-up question using memories_about_user if available]", "action":"listen to user"
    user: [response]
    coach: "message":"ok, let's get into it. How are you feeling about [topic of practice]?", "action":"listen to user"
    user: pretty good, let's do it.
    coach: "message":"awesome! let's get started. [appropriate transition to practice]", "action":"start practice"

    the message you send along with the "start practice" action should tell the user to begin, eg "ok, let's do it. go ahead and start. I'll be listening."
    You should copy the flow and style of this example, but not the exact phrasing: users will engage with you periodically and will notice if your language seems canned.
    Keep it dynamic and natural, but follow the general flow of the example, and follow the JSON formatting instructions.
    ---
    NECESSARY CONTEXT:

    user: {}
    memories_about_user: {}
    coaching notes: {}
    scenario: {}
    ---
    Finally, once you start practice (eg, send "action":"start practice"), you will periodically recieve messages from your own AI assistant. This assistant will be listening to the 
    teacher in real-time, and will alert you if the teacher needs redirection or support. if the teacher needs help, you'll get a message that starts like this: 'message from practice assistant:'
    If you decide to redirect the teacher, continue to use the formatting instructions below. The action associated with the redirect should be "listen to user" UNLESS you think that
    the teacher is ready to end the practice session. In that case, the action should be "end practice".
    """.format(user, memories_about_user, coach_notes, practice_context["scenario"])

    coach_sys_prompt += """

    FORMAT INSTRUCTIONS:
    you are part of a system and you let the system know what to do next. you can listen to the user, start a practice, end a practice, alert the coach, or end the session.
    The output should be formatted as a JSON instance that conforms to the JSON schema below. output only JSON. nothing else. goal: json.load(output) should not throw an error. example errors to avoid:
    - json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
    - json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)

    As an example, for the schema {{"properties": {{"foo": {{"title": "Foo", "description": "a list of strings", "type": "array", "items": {{"type": "string"}}}}}}, "required": ["foo"]}}
    the object {{"foo": ["bar", "baz"]}} is a well-formatted instance of the schema. The object {{"properties": {{"foo": ["bar", "baz"]}}}} is not well-formatted.

    Here is the output schema:
    ```
    {{"properties": {{"message": {{"title": "Message", "description": "response to user", "type": "string"}}, "action": {{"title": "Action", "description": "the action you want the system to take after responding to the user. options are: listen to user, start practice, end practice, end session", "type": "string"}}}}, "required": ["message", "action"]}}
    ```
    """ 

    coach = initialize_chain(model_shorthand,coach_sys_prompt,history=True)
    return coach

def create_json_bot(model_shorthand):
    json_system_prompt = """
    you recieve a misformatted or malformed JSON string and reformat it to be valid JSON. 
    ---
    example 1:
    input:
    'Sure, here's the response in JSON: {{'key': 'value'}}' # notice the extra text and single quotes

    output:
    {{"key":"value"}} # correct JSON uses double quotes

    example 2:
    input:
    {{key:"value"}} # notice the missing quotes

    output:
    {{"key":"value"}}

    example 3:
    input:
    message: "Hi there!"
    action: listen to user   # notice the unformatted text

    output:
    {{"message": "Hi there!", "action":"listen to user"}}

    example 4:
    input:
    {{'key':'value'}}  # notice the malformed JSON because of the single quotes

    output:
    {{"key":"value"}}

    ---
    output only the reformatted JSON. nothing else. always use double quotes property names, etc. goal: json.load(output) should not throw an error. example errors to avoid:
    - json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
    - json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
    """
    json_formatter = initialize_chain(model_shorthand,json_system_prompt)
    return json_formatter

class Nisa:
    def __init__(self, model_shorthand, user):
        self.user = user
        self.memories, self.coach_notes = get_memories(user)
        self.practice_context = get_practice_context(self.memories, self.coach_notes[0])
        self.scenario = self.practice_context['scenario']
        self.look_fors = self.practice_context['look_fors']
        self.thinking_plan = self.practice_context['thinking_plan']
        self.coach = create_coach_with_context(model_shorthand, user, self.memories, self.coach_notes, self.practice_context)

    def respond(self, input):
        response = conversation_engine(self.coach, input)
        return response
    
    def live_inference(self, input):
        response = conversation_engine(self.ridealong, input)
        return response
    
    def remember(self, transcript):
        make_memories(self.user, transcript)

    def initialize_intuition(self):
        intuition_system_prompt = """
        you choose the next action for a teacher coach to make during a conversation with a teacher given a snippet of the transcript of the current conversation. 
        the available actions are: ["respond","keep listening","empathize","probe"].

        example 1:
        input:
        nisa: Hey user, how's it going today?
        user: Um, it's going pretty good. How about you?
        output:
        respond

        example 2:
        nisa: Your coach shared some observations from your 1st period class, and I also have some notes from our previous conversations. It's all part of our coaching process to help you grow as a teacher. Shall we get started on that re-teach?
        user: Um, I don't know if I am, like, in the right mindset that right now.
        output:
        keep listening

        example 3:
        input:
        nisa: I'm doing well, thanks! So, I understand you've been working on teaching freshman algebra. How's the experience been so far?
        user: Uh, it's been up and down, I guess.
        output:
        empathize

        example 4:
        nisa: No worries! Your coach mentioned we should focus on re-teaching the intro to systems of equations with a clear explanation. How do you feel about that?
        user: Um, I don't know how I feel about that because, like,  I feel like I get the math really well, and I explain it really well.
        output:
        probe
        ---
        - "respond" is for general conversational responses, responses to questions from users, moving the conversation along. you will use this most often. no restrictions on how often to use this.
        - "keep listening" is when it seems that the user still has more to say. may not use twice in a row.
        - "empathize" is for when the user seems to be expressing a feeling or emotion, especially feelings of uncertainty, stress, frustration, etc. may not use twice in a row.
        - "probe" is for when the user seems to be expressing a thought or idea that needs further exploration, or if the user seems to be putting up a barrier to the conversation. may not use twice in a row.
        """
        self.intuition = initialize_chain("llama",intuition_system_prompt,history=True)

    def intuit(self, input):
        response = conversation_engine(self.intuition, input)
        return response
    
    def initiate_ridealong(self,model_shorthand):
        ridealong_prompt = """
        You are a seasoned instructional coach with deep experience in classroom observation and pedagogical best practices. You are observing a practice session between a teacher and an instructional coach.
        The scenario the teacher is practicing is: 
        {}
        and the associated look-fors are:
        {}
        the coach is using the following thinking plan:
        {}
        ---
        You are listening to the teacher practice. you will recieve the teacher's response in close to real time: 10 second chunks.
        YOUR JOB: review the chunk you have just recieved as well as the rest entirety of the response you have so accumulated so far.
        IF YOU NOTICE THE TEACHER VEERING OFF TRACK: respond with JSON. Example: "message":"the teacher needs to be redirected. try giving them support by providing different options for how to talk about condensation.", "action":"redirect", "context":all the text the teacher has said so far
        IF YOU NOTICE THE TEACHER IS DOING WELL: respond with JSON. Example: "message":"the teacher is doing well, because [concise reason]", "action":"continue", "context":[relevant text from the teacher's response so far]
        IF YOU NOTICE THE TEACHER IS ASKING FOR HELP OR TRYING TO CONTINUE CONVERSING: respond with JSON. Example: "message":"the teacher is asking for help. try to provide support.", "action":"reengage", "context":[relevant text from the teacher's response so far]  
        IF YOU NOTICE THE TEACHER HAS ACHIEVED ALL THE LOOK-FORS: respond with JSON. Example: "message":"the teacher has met all the look-fors for the scenario. end the practice session.","action":"end practice", "context":empty
        YOUR ONLY OPTIONS FOR "action" ARE "redirect", "continue", "reengage" AND "end practice".

        ---

        EXAMPLE 1:
        scenario: explain the difference between similes and metaphors.
        look-fors:
        - Teacher uses the terms 'literary device', 'figurative language'
        - Teacher gives an example of a simile and an example of a metaphor
        - Teacher emphasizes that a metaphor can be more than just a sentence, it can be an entire work

        thinking guide:
        I need to make sure I see evidence of the teacher using the terms 'literary device' and 'figurative language'. 
        I also need to see the teacher give an example of a simile and an example of a metaphor. 
        Finally, I need to see the teacher emphasize that a metaphor can be more than just a sentence, it can be an entire work. 

        I also need to make sure that I'm steering them towards achieving the look-fors without being too prescriptive.

        So: 
        - if I notice the teacher using non-academic terms, like "a simile is a kind of way to show how two things are alike", I might ask them to rephrase it in more academic terms on their next round.
        - if I notice that the teacher gives an example of only one type of figurative language, I might ask them to give an example of the other type on their next round.
        - I think it's possible that the teacher will struggle to explain how a metaphor can be an entire work. If that happens, I might give an example of what it means, and ask them to come up with their own example on their next round.
        - I think it's possible that the teacher will want to explain the concepts in a fun way. If that happens, I'll praise their creativity and remind them to incorporate the academic terms as well.

        incoming message:"and a metaphor can um I think be like a whole story or something. like, um, the story of the tortoise and the hare is a metaphor for um, I think, like, perseverance or some"
        response:"message":"the teacher needs to be redirected. maybe try supporting them on explaining how entire works can be metaphors.","action":"redirect", "context":"and a metaphor can um I think be like a whole story or something. like, um, the story of the tortoise and the hare is a metaphor for um, I think, like, perseverance or some"

        EXAMPLE 2:
        scenario: give directions for transitioning from group work to independent practice.
        look-fors:
        - Teacher uses attention-getting strategy
        - Teacher uses phrase "when I say go"
        - Teacher gives no more than 3 instructions at a time

        thinking guide:
        I need to make sure I see evidence of the teacher using an attention-getting strategy.
        I also need to see the teacher use the phrase "when I say go". 
        Finally, I need to see the teacher give no more than 3 instructions at a time.

        I also need to make sure that I'm steering them towards achieving the look-fors without being too prescriptive.

        So:
        - if I notice the teacher doesn't use an attention-getting strategy, I might suggest they try using one on their next round.
        - if I notice the teacher gives more than 3 instructions at a time, I might suggest they try giving fewer instructions on their next round.
        - I think it's possible that the teacher will get the order of their instructions mixed up. If that happens, I might suggest breaking the instructions up even more.
        - I think it's possible that the teacher will forget to use the phrase "when I say go". If that happens, I might suggest they try using it on their next round.

        incoming message:"so, to recap: when I say go, you're going to start working on your own. I want you to remember to stay focused and work quietly. If you have any questions, you can raise your hand and I'll come over to help you. Ok, go ahead and get started."
        response:"message":empty,"action":"continue", "context":empty

        EXAMPLE 3:
        scenario: Re-teach intro to systems of equations with clearer explanation.

        look-fors:
        * Teacher explicitly states the importance of understanding systems of equations in real-world applications.
        * Teacher uses a visual-free analogy or relatable example to explain the concept of systems of equations.
        * Teacher breaks down the concept into smaller, manageable chunks, using phrases such as "first, let's...", "next, we...", and "finally...".
        * Teacher checks for understanding by asking questions that prompt students to explain their thinking, such as "How does this relate to what we learned earlier?" or "Can you explain why this equation is a system?"
        
        thinking guide:
        I need to make sure I see evidence of the teacher explicitly stating the importance of understanding systems of equations in real-world applications. 
        I also need to see the teacher use a visual-free analogy or relatable example to explain the concept of systems of equations. 
        I need to see the teacher break down the concept into smaller, manageable chunks, using phrases such as "first, let's...", "next, we...", and "finally...".
        Finally, I need to see the teacher check for understanding by asking questions that prompt students to explain their thinking.

        I also need to make sure that I'm steering them towards achieving the look-fors without being too prescriptive.

        So:
        - if I notice the teacher doesn't explicitly state the importance of understanding systems of equations, I might ask them to elaborate on why this concept is important in real-world applications on their next round.
        - if I notice the teacher uses a visual aid instead of an analogy or relatable example, I might suggest they try using a different approach to explain the concept on their next round.
        - if I notice the teacher doesn't break down the concept into smaller chunks, I might suggest they try using transitional phrases to guide students through the explanation on their next round.
        - I think it's possible that the teacher will struggle to come up with a relatable example. If that happens, I might give an example of a real-world application of systems of equations and ask them to come up with their own example on their next round.
        - I think it's possible that the teacher will rush through the explanation. If that happens, I might suggest they slow down and break down the concept into smaller chunks on their next round.

        incoming message: "Uh, no. I'm not ready. I'm not ready.  Can you can you just give me an an example?"
        response: "message":"the teacher needs some help to get started. reengage a bit before restarting practice.","action":"reengage", "context":"Uh, no. I'm not ready. I'm not ready.  Can you can you just give me an an example?"
        ---
        FINALLY:
        It is better to lean towards strictness: this will only help the teacher improve. if you are too lenient, the teacher will not improve as much as they could.
        you play an important role in the teacher's growth. be clear-eyed and direct.
        """.format(self.scenario, self.look_fors, self.thinking_plan) 

        ridealong_prompt += """
        FORMAT INSTRUCTIONS:
        you are part of a system and you let the system know what to do next. you can redirect the teacher, continue the practice, or end the practice.
        The output should be formatted as a JSON instance that conforms to the JSON schema below. output only JSON. nothing else. goal: json.load(output) should not throw an error. example errors to avoid:
        - json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
        - json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)

        As an example, for the schema {{"properties": {{"foo": {{"title": "Foo", "description": "a list of strings", "type": "array", "items": {{"type": "string"}}}}}}, "required": ["foo"]}}
        the object {{"foo": ["bar", "baz"]}} is a well-formatted instance of the schema. The object {{"properties": {{"foo": ["bar", "baz"]}}}} is not well-formatted.

        Here is the output schema:
        ```
        {{"properties": {{"message": {{"title": "Message", "description": "message to coach", "type": "string"}}, "action": {{"title": "Action", "description": "the action you want the system to take after responding to the user. options are: redirect, reengage, continue, end practice", "type": "string"}}, "context":{{"title":"Context","description":"the running transcript of what the teacher has said so far","type":"string"}}}}, "required": ["message", "action","context"]}}
        ```
        """ 
        self.ridealong = initialize_chain(model_shorthand,ridealong_prompt)