import pyttsx3
from moviepy.editor import AudioFileClip

engine = pyttsx3.init()
voices = engine.getProperty("voices")
for voice in voices:
    print(voice, voice.id)
    engine.setProperty("voice", voice.id)
    engine.say("Hello World!")
    engine.runAndWait()
    clip = AudioFileClip(f"hello_world.mp3")
    clip.close()
    engine.stop()
