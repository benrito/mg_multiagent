import random
import pygame
from playsound import playsound
import os
import threading
import time
import subprocess
import json

from lib.plantoid.text_content import *
import lib.plantoid.speech as PlantoidSpeech
import lib.plantoid.serial_utils as PlantoidSerial
import lib.plantoid.web3_utils as web3_utils

class Plantony:

    def __init__(self, serial_connector, eleven_voice_id):

        # instantaite serial connector
        self.serial_connector = serial_connector

        # user and agent names
        self.USER = "Human"
        self.AGENT = "Plantoid"

        # a list of events
        self._events = {}

        # whether to use the Arduino or not
        self.use_arduino = True

        # lines for the opening and closing
        self.opening = ""
        self.closing = ""
        self.prompt_text = ""

        # eleven voice id
        self.eleven_voice_id = eleven_voice_id

        # a round will contain a series of turns
        self.rounds = [[]]

        # # a turn will contain a series of interactions
        # self.turns = []

        # load the text content
        self.opening_lines, self.closing_lines, self.word_categories = get_text_content()

        # load chat personality
        self.chat_personality = get_ai_chat_personality()

        # Load the sounds
        self.acknowledgements = [
            os.getcwd()+"/media/hmm1.mp3",
            os.getcwd()+"/media/hmm2.mp3",
        ]

        # Load the sounds
        self.introduction = os.getcwd()+"/samples/intro1.mp3"
        self.outroduction = os.getcwd()+"/samples/outro1.mp3"
        self.reflection = os.getcwd()+"/media/initiation.mp3"
        self.cleanse = os.getcwd()+"/media/cleanse.mp3"

    # def ambient_background(self, music, stop_event):

    #     while not stop_event.is_set():
    #         playsound(music)

    def add_listener(self, event_name, callback):

        # add the callback to the list of listeners
        if event_name not in self._events:
            self._events[event_name] = []
        
        # add the callback to the list of listeners
        self._events[event_name].append(callback)

    def remove_listener(self, event_name, callback):

        # remove the callback from the list of listeners
        if event_name in self._events:
            self._events[event_name].remove(callback)

    def trigger(self, event_name, *args, **kwargs):

        # trigger the event
        if event_name in self._events:
            for listener in self._events[event_name]:
                listener(*args, **kwargs)

    def setup(self):

        # load the personality of Plantony
        self.prompt_text = open(os.getcwd()+"/prompt_context/plantony_context.txt").read().strip()

        # select a random opening and closing line
        self.opening = random.choice(self.opening_lines)
        self.closing = random.choice(self.closing_lines) 

        # create a round
        self.append_turn_to_round(self.AGENT, self.opening)

        # for Plantony oracle
        self.selected_words = []

        # select one item from each category
        for category in self.word_categories:
            self.selected_words.append(random.choice(category['items']))

        # join the selected words into a comma-delimited string
        self.selected_words_string = ', '.join(self.selected_words)

        # print the result
        print("Plantony is setting up. His seed words are: " + self.selected_words_string)

    def send_serial_message(self, message):

        if self.use_arduino:
            PlantoidSerial.send_to_arduino(self.serial_connector, message)

    def play_background_music(self, filename, loops=-1):
        pygame.mixer.init()
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play(loops)

    def stop_background_music(self):
        print('stop background music')
        pygame.mixer.music.stop()

    def get_voice_id(self):

        return self.eleven_voice_id

    def welcome(self):

        print('Plantony Welcome!')
        print(self.introduction)

        self.send_serial_message("speaking")

        playsound(self.introduction)
        
        audiofile = PlantoidSpeech.get_text_to_speech_response(self.opening, self.eleven_voice_id)
        print('plantony opening', self.opening)
        print("welcome plantony... opening = " + audiofile)
    
        playsound(audiofile)

    def terminate(self):

        self.send_serial_message("speaking")

        print('plantony closing', self.closing)
        playsound(PlantoidSpeech.get_text_to_speech_response(self.closing, self.eleven_voice_id)) 
        playsound(self.outroduction)

        self.send_serial_message("asleep")

    def listen(self, use_whisper=False):

        self.send_serial_message("listening")

        if use_whisper:

            audio = PlantoidSpeech.listen_for_speech_whisper()

        else:

            audio = PlantoidSpeech.listen_for_speech()

            print("Plantony listen is returning the audiofile as:  " + audio)

        playsound(self.acknowledge())

        return audio

    def respond(self, audio, use_whisper=False):

        def prompt_agent_and_respond(audio, callback):
            
            # user text received from speech recognition
            user_message = PlantoidSpeech.recognize_speech(audio)

            print("I heard... " + user_message)

            if len(user_message) == 0:
                print('no text heard, using default text')
                user_message = "Hmmmmm..."

            # append the user's turn to the latest round
            self.append_turn_to_round(self.USER, user_message)

            agent_prompt = self.update_prompt()

            # generate the response from the GPT model
            agent_message = PlantoidSpeech.GPTmagic(agent_prompt, call_type='chat_completion')

            # append the agent's turn to the latest round
            self.append_turn_to_round(self.AGENT, agent_message)

            # get audio file from TTS repsonse
            audio_file = PlantoidSpeech.get_text_to_speech_response(agent_message, self.eleven_voice_id, callback=callback)

            # Tsend speech signal
            self.send_serial_message("speaking")

            # play the audio file
            playsound(audio_file)

        def prompt_agent_and_respond_whisper(audio, callback):
            
            # user text received from speech recognition
            user_message = audio

            print("I heard... " + user_message)

            if len(user_message) == 0:
                print('no text heard, using default text')
                user_message = "Hmmmmm..."

            # append the user's turn to the latest round
            self.append_turn_to_round(self.USER, user_message)

            # TODO: figure out what to do here
            # agent_prompt = self.update_prompt()

            # generate the response from the GPT model
            agent_message = PlantoidSpeech.get_chat_response(self.chat_personality, audio)

            # append the agent's turn to the latest round
            self.append_turn_to_round(self.AGENT, agent_message)

            # send serial message
            self.send_serial_message("speaking")

            # stream audio response
            PlantoidSpeech.stream_audio_response(agent_message, self.get_voice_id(), callback=callback)

        self.send_serial_message("thinking")

        print("Plantony respond is receiving the audiofile as : " + audio)

        # get the path to the background music
        background_music_path = os.getcwd()+"/media/ambient3.mp3"

        # play the background music
        self.play_background_music(background_music_path)

        # if use whisper
        if use_whisper:

            # prompt agent and respond
            prompt_agent_and_respond_whisper(audio, self.stop_background_music)
        
        else:

            # prompt agent and respond
            prompt_agent_and_respond(audio, self.stop_background_music)

    def acknowledge(self):

        return random.choice(self.acknowledgements)

    def append_turn_to_round(self, agent, text):

        # initialize turn data
        turn_data = { "speaker": agent, "text": text }

        # append turn data to latest round
        self.rounds[-1].append(turn_data)

    def create_round(self):
        
        # create a new round
        self.rounds.append([])

    def reset_rounds(self):

        # reset the rounds
        self.rounds = []

    def update_prompt(self):

        # create a transcript from the rounds
        lines = []
        transcript = ""

        # iterate through the rounds
        for turns in self.rounds:

            # iterate through the turns
            for turn in turns:

                text = turn["text"]
                speaker = turn["speaker"]
                lines.append(speaker + ": " + text)

        # join the lines into a single string
        transcript = "\n".join(lines)

        return self.prompt_text.replace("{{transcript}}", transcript)
    
    def get_prompt(self):
        
        return self.prompt_text

    def reset_prompt(self):

        # load the personality of Plantony
        self.prompt_text = open(os.getcwd()+"/prompt_context/plantony_context.txt").read().strip()

        
    def weaving(self):
        
        self.send_serial_message("speaking")

        playsound(self.reflection)

    def generate_oracle(self, network, audio, tID, amount):

        self.send_serial_message("thinking")

        # get the path of the network
        path = network.path

        # get the path to the background music
        background_music_path = os.getcwd()+"/media/ambient3.mp3"

        # play the background music
        self.play_background_music(background_music_path)

        # get generated transcript
        generated_transcript = PlantoidSpeech.recognize_speech(audio)

        # print the generated transcript
        print("I heard... (oracle): " + generated_transcript)

        # if no generated transcript, use a default
        if not generated_transcript: 
            generated_transcript = get_default_sermon_transcript()

        # save the generated transcript to a file with the seed name
        if not os.path.exists(path + "/transcripts"):
            os.makedirs(path + "/transcripts");

        # save the generated response to a file with the seed name
        filename = path + f"/transcripts/{tID}_transcript.txt"
        with open(filename, "w") as f:
            f.write(generated_transcript)

        print("transcript saved as ..... " + filename)

        # TODO: re-enable
        # calculate the length of the poem
        # one line every 0.01 ETH for mainnet, one line every 0.001 ETH for goerli
        n_lines = int(amount / network.min_amount)  
        
        if n_lines > 6: 
            n_lines = 6

        # n_lines = 4

        print("generating transcript with number of lines = " + str(n_lines))
        
        # generate the sermon prompt
        prompt = get_sermon_prompt(
            generated_transcript,
            self.selected_words_string,
            n_lines
        )
        
        # get GPT response
        response = PlantoidSpeech.GPTmagic(prompt, call_type='completion')
        sermon_text = response.choices[0].text

        print('sermon text:')
        print(sermon_text)

        responses_path = path + "/responses"
        responses_path_network = path + "/responses/" + str(network.name)

        # save the generated response to a file with the seed name
        if not os.path.exists(responses_path):
            os.makedirs(responses_path);

        # save the generated response to a file with the seed name
        if not os.path.exists(responses_path_network):
            os.makedirs(responses_path_network);
        
        # save the generated response to a file with the seed name
        filename = path + f"/responses/{network.name}/{tID}_response.txt"
        with open(filename, "w") as f:
            f.write(sermon_text)

        # now let's print to the LP0, with Plantoid signature
        # TODO: figure out what this is meant to do
        plantoid_sig = get_plantoid_sig(network, tID)

        # TODO: figure out what this is meant to do
        # os.system("cat " + filename + " > /dev/usb/lp0") #stdout on PC, only makes sense in the gallery
        # os.system("echo '" + plantoid_sig + "' > /dev/usb/lp0")

        # now let's read it aloud
        audiofile = PlantoidSpeech.get_text_to_speech_response(sermon_text, self.eleven_voice_id)
        # stop_event.set() # stop the background noise

        sermons_path = path + "/sermons"
        sermons_path_network = path + "/sermons/"+str(network.name)

        # save the generated sermons to a file with the seed name
        if not os.path.exists(sermons_path):
            os.makedirs(sermons_path)

        if not os.path.exists(sermons_path_network):
            os.makedirs(sermons_path_network)
        
        # save mp3 file
        # subprocess.run(["cp", audiofile, f"{path}/sermons/{tID}_sermon.mp3"])
        subprocess.run(["cp", audiofile, f"{sermons_path_network}/{tID}_sermon.mp3"])

        # stop the background music
        self.stop_background_music()

        # play the oracle
        self.read_oracle(audiofile)

    # TODO: try to queue these
    def read_oracle(self, filename):

        self.send_serial_message("speaking")
        
        # playsound(filename)
        self.play_background_music(filename, loops=0)
        time.sleep(1)

        self.send_serial_message("asleep")
        
        # # playsound(self.cleanse)
        # self.play_background_music(self.cleanse, loops=0)

        print('oracle read completed!')


    def check_if_fed(self, network):

        ### this returns the token ID and the amount of wei that plantoid has been fed with
        latest_deposit  = web3_utils.check_for_deposits(network) 

        # If Plantoid has been fed
        if latest_deposit is not None:  

            print('deposit found!')
        
            # get the token ID and the amount of wei that plantoid has been fed with
            (token_Id, amount) = latest_deposit

            print("got amount " + str(amount) + " for id = " + token_Id)

            # do weaving
            self.weaving()
        
            # listen for audio
            audiofile = self.listen()

            print('Early termination of check if fed.')
        
            # generate the oracle
            self.generate_oracle(network, audiofile, token_Id, amount)

            self.send_serial_message("thinking")
        
            # create the metadata
            web3_utils.create_seed_metadata(network, token_Id)

            # pin the metadata to IPFS and enable reveal link via metatransaction
            web3_utils.enable_seed_reveal(network, token_Id)

            self.send_serial_message("asleep")


        else:

            print("sorry, no deposits detected. try later.")

            # # listen for audio
            # audiofile = self.listen()
            # tID = '0xABC'
            # amount = 0.001

            # # generate the oracle
            # self.generate_oracle(network, audiofile, tID, amount)

            # # create the metadata
            # web3_utils.create_seed_metadata(network, tID)


