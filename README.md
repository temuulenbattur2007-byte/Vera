# \# 🤖 Vera — Local AI Companion

# 

# A sharp, witty, loyal AI companion powered by \*\*Qwen2.5-7B-Instruct Q6\*\* that runs \*\*100% locally\*\* on your Windows laptop.

# 

# She can:

# \- Control your laptop (volume, apps, browser, shutdown/restart)

# \- Remember past conversations day by day

# \- Search the web for current info

# \- Be your psychological companion

# \- Learn your preferences over time via fine-tuning

# 

# \---

# 

# \## 📁 Project Structure

# 

# ```

# Vera/

# ├── gui.py               ← Run this to start Vera (GUI)

# ├── main.py              ← Terminal version

# ├── persona.py           ← Her personality \& system prompt

# ├── config.py            ← All settings in one place

# ├── model\_loader.py      ← Loads the GGUF text model

# ├── model\_loader\_vl.py   ← Loads the vision model

# ├── tool\_registry.py     ← Maps JSON commands → Python functions

# ├── finetune.py          ← Fine-tune Vera on your conversations

# ├── requirements.txt     ← All dependencies

# ├── Vera.bat             ← Double-click launcher

# │

# ├── tools/

# │   ├── volume.py        ← Volume up/down/mute/set

# │   ├── media.py         ← Play/pause/skip/stop/music

# │   ├── apps.py          ← Open apps, URLs, folders

# │   ├── system.py        ← Shutdown/restart/sleep/lock

# │   ├── reminder.py      ← Reminders with toast notifications

# │   ├── tts.py           ← Text-to-speech via Piper

# │   ├── voice\_pipeline.py← Wake word + Whisper STT

# │   ├── web\_search.py    ← Tavily web search

# │   └── volume.py        ← Windows volume control

# │

# ├── memory/

# │   ├── short\_term.py    ← Rolling conversation history (RAM)

# │   ├── daily\_log.py     ← Daily JSON logs (logs/YYYY-MM-DD.json)

# │   ├── vector\_store.py  ← Long-term semantic memory (ChromaDB)

# │   ├── rag.py           ← Document search (PDFs, docx, txt)

# │   └── startup.py       ← Loads past context on startup

# │

# ├── model/               ← Put your .gguf model file here

# ├── voices/              ← Piper TTS voice files

# ├── logs/                ← Auto-created: daily conversation logs

# ├── chroma\_db/           ← Auto-created: long-term memory database

# └── documents/           ← Drop files here for Vera to search

# ```

# 

# \---

# 

# \## 🚀 Setup

# 

# \### Step 1 — Model

# Your model is already in `model/Qwen2.5-7B-Instruct-1M-Q6\_K.gguf`. ✅

# 

# \### Step 2 — Install dependencies

# ```bash

# pip install -r requirements.txt

# ```

# 

# For GPU (CUDA):

# ```bash

# pip uninstall llama-cpp-python -y

# pip install llama-cpp-python\[cuda]

# ```

# 

# \### Step 3 — Run

# Double-click `Vera.bat` or run:

# ```bash

# python gui.py

# ```

# 

# \---

# 

# \## 💬 Usage

# 

# Just talk naturally. Vera understands context and intent.

# 

# | You say | Vera does |

# |---|---|

# | `volume up` | Increases volume |

# | `open YouTube` | Opens browser to youtube.com |

# | `open downloads` | Opens Downloads folder |

# | `open Spotify` | Launches Spotify |

# | `restart my laptop` | Asks confirmation, then restarts |

# | `play music` | Plays music from your Music folder |

# | `remind me in 2 hours to eat` | Sets a reminder |

# | `what's the weather today` | Searches the web |

# | `I'm stressed` | Switches to companion mode |

# 

# \---

# 

# \## 🛠️ Special Commands

# 

# | Command | Effect |

# |---|---|

# | `/help` | Show all commands |

# | `/memory` | Show memory stats |

# | `/days` | List all logged days |

# | `/day 2026-05-01` | Show that day's summary |

# | `/save I hate mornings` | Manually save a long-term memory |

# | `/websearch <query>` | Search the web |

# | `/quit` | End session and save memory |

# 

# \---

# 

# \## 🧠 How Memory Works

# 

# \*\*Layer 1 — Short-Term (Current Session)\*\*

# The last 40 messages are kept in RAM. Vera follows your conversation naturally.

# 

# \*\*Layer 2 — Daily Log (Disk)\*\*

# Every session is saved to `logs/YYYY-MM-DD.json`. At the end of each session, Vera writes a summary of what you discussed, your mood, and key facts.

# 

# \*\*Layer 3 — Long-Term (ChromaDB)\*\*

# Key facts and notable moments are stored as vectors. When you bring up something related, Vera retrieves the relevant memory and weaves it in naturally.

# 

# \*\*Layer 4 — Document RAG\*\*

# Drop any PDF, Word doc, or text file into the `documents/` folder. Vera will index it and search it when answering relevant questions.

# 

# \---

# 

# \## 🎙️ Voice

# 

# \- Click \*\*👂 OFF\*\* in the top bar to enable always-on voice

# \- Say \*\*"Hey Vera"\*\* to wake her up

# \- Speak your command — she transcribes with Whisper and responds

# \- Click \*\*🔊\*\* to enable text-to-speech so she talks back

# 

# \---

# 

# \## ✏️ Customization

# 

# Edit `config.py` to change:

# \- `USER\_NAME` — your name

# \- `VERA\_NAME` — her name

# \- `GPU\_LAYERS` — how many layers to offload to GPU

# \- `CTX\_SIZE` — context window size

# \- `TEMPERATURE` — response creativity

# 

# Edit `persona.py` to change her personality.

# 

# \---

# 

# \## 🔧 Troubleshooting

# 

# \*\*"Model not found"\*\* → Check `MODEL\_PATH` in `config.py`

# 

# \*\*"pycaw not available"\*\* → `pip install pycaw comtypes` (volume still works via fallback)

# 

# \*\*Model is slow\*\* → Increase `GPU\_LAYERS` in `config.py`

# 

# \*\*Vera outputs raw text instead of JSON\*\* → Lower `TEMPERATURE` to `0.5` in `config.py`

# 

# \---

# 

# \## 📦 Key Libraries

# 

# | Library | Purpose |

# |---|---|

# | `llama-cpp-python` | Runs the GGUF model locally |

# | `chromadb` | Vector database for long-term memory |

# | `pycaw` | Precise Windows volume control |

# | `pyautogui` | Media key simulation |

# | `faster-whisper` | Local speech-to-text |

# | `piper` | Local text-to-speech |

# | `rich` | Terminal UI styling |

# 

# \---

# 

# \*Built for local use. No data ever leaves your machine.\*

