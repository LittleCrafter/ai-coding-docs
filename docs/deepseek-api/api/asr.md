# Speech to Text

Copy MarkdownCopy Markdown

[Open Markdown](<https://api-docs.deepseek.com/api/asr.md> "Open Markdown in a new tab")

```
POST /v1/tools/asr
```

Transcribe an audio file into text. The whole file is sent in one request and the complete transcript is returned. See the [Speech to Text guide](<../guides/asr.md>) for the languages, limits, errors and billing.

## Request

**multipart/form-data**

### Body

**

required

**

**file** binaryrequired

The audio file: 16-bit PCM WAV or Ogg Opus. See the [Speech to Text guide](<../guides/asr.md>) for the limits.

## Responses

**200**

OK, returns the transcript.

**application/json**

**Schema**

**

Schema

**

**request_id** stringrequired

The request ID.

**text** stringrequired

The transcript.

**duration_ms** integerrequired

The duration of the audio, in milliseconds.

**Example**

```json
{
  "request_id": "0b8c1c7e-3c0e-4d0f-9d3a-5f2a6f7e8b90",
  "text": "What is the weather like in Shanghai today?",
  "duration_ms": 3200
}
```

Loading...