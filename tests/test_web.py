import pytest
from fastapi.testclient import TestClient

from tutor.config import Settings
from tutor.web.app import create_app


@pytest.fixture
def client(content, fake_speech):
    fake_speech.reset()
    app = create_app(content=content, speech=fake_speech, settings=Settings(bot_username="english_tutor_bot"))
    return TestClient(app)


def test_index_and_static(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "English Tutor" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_overview(client, content):
    data = client.get("/api/overview").json()
    assert data["grammar"] == len(content.grammar)
    assert data["bot_url"] == "https://t.me/english_tutor_bot"


def test_grammar_hides_answers(client):
    lessons = client.get("/api/grammar").json()
    assert lessons[0]["id"] == "to-be"
    lesson = client.get("/api/grammar/present-simple").json()
    assert "<table>" in lesson["theory_html"]
    assert lesson["examples"]
    for exercise in lesson["exercises"]:
        assert "answer" not in exercise and "answers" not in exercise and "explanation" not in exercise


def test_grammar_check(client):
    ok = client.post("/api/grammar/present-simple/check", json={"question_id": "1", "answer": 1}).json()
    assert ok["correct"] is True
    typed = client.post("/api/grammar/present-simple/check", json={"question_id": "8", "answer": "does not like"}).json()
    assert typed["correct"] is True
    wrong = client.post("/api/grammar/present-simple/check", json={"question_id": "6", "answer": "studys"}).json()
    assert wrong == {"correct": False, "correct_answer": "studies", "explanation": wrong["explanation"], "given": "studys"}


def test_not_found(client):
    assert client.get("/api/grammar/nope").status_code == 404
    assert client.get("/api/tests/nope").status_code == 404
    assert client.post("/api/tests/placement/check", json={"question_id": "999", "answer": 0}).status_code == 404
    assert client.post("/api/dialogues/cafe/check", json={"turn": 99, "answer": "hi"}).status_code == 404


def test_tests_flow(client, content):
    tests = client.get("/api/tests").json()
    assert {t["id"] for t in tests} == {t["id"] for t in content.tests}
    placement = client.get("/api/tests/placement").json()
    assert placement["grading"][0] == [0, "A1"]
    q = content.test("placement")["questions"][0]
    res = client.post("/api/tests/placement/check", json={"question_id": q["id"], "answer": q["answer"]}).json()
    assert res["correct"]


def test_listening(client, content):
    data = client.get("/api/listening").json()
    assert len(data["dictation"]) == len(content.dictation)
    assert "answer" not in data["comprehension"][0]["questions"][0]
    item = content.dictation[0]
    res = client.post(f"/api/listening/dictation/{item['id']}/check", json={"answer": item["text"]}).json()
    assert res["score"] == 100 and res["text"] == item["text"] and res["ru"] == item["ru"]
    text = content.comprehension[0]
    q = text["questions"][0]
    res = client.post(f"/api/listening/comprehension/{text['id']}/check", json={"question_id": q["id"], "answer": q["answer"]}).json()
    assert res["correct"]


def test_speaking(client):
    data = client.get("/api/speaking").json()
    assert data["topics"] and data["phrases"] and data["questions"]
    score = client.post("/api/score", json={"expected": "Nice to meet you.", "actual": "nice to meet you"}).json()
    assert score["score"] == 100
    res = client.post("/api/speaking/questions/q-name/check", json={"answer": "My name is Tom and I am from Lviv"}).json()
    assert res["enough"] is True and res["sample"]


def test_dialogues(client):
    listing = client.get("/api/dialogues").json()
    assert any(d["id"] == "cafe" for d in listing)
    dialogue = client.get("/api/dialogues/cafe").json()
    assert dialogue["turns"][0]["line"]
    ok = client.post("/api/dialogues/cafe/check", json={"turn": 0, "answer": "A latte, please"}).json()
    assert ok["accepted"] is True
    bad = client.post("/api/dialogues/cafe/check", json={"turn": 0, "answer": "What is the time?"}).json()
    assert bad["accepted"] is False and bad["hint"]


def test_tts(client, fake_speech):
    res = client.get("/api/tts", params={"text": "Hello there", "slow": "true"})
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/mpeg"
    assert fake_speech.synthesized == [("Hello there", True)]
    assert client.get("/api/tts", params={"text": ""}).status_code == 422
    fake_speech.fail_tts = True
    assert client.get("/api/tts", params={"text": "Hello"}).status_code == 503


def test_stt(client, fake_speech):
    fake_speech.transcript = "hello world"
    res = client.post("/api/stt", files={"audio": ("speech.webm", b"fake-audio", "audio/webm")})
    assert res.status_code == 200
    assert res.json() == {"text": "hello world"}
    fake_speech.fail_stt = True
    res = client.post("/api/stt", files={"audio": ("speech.webm", b"fake-audio", "audio/webm")})
    assert res.status_code == 503
