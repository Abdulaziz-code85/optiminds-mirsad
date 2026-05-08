"""
Mirsad - Multi-Agent Guardian for Hajj & Umrah
Hugging Face Spaces deployment.
Team Optiminds - Agenticthon 2026
"""

import os
import json
import random
import time
import math
import concurrent.futures
from datetime import datetime

import google.generativeai as genai
import gradio as gr
import folium


# ============================================================
# 1. GEMINI SETUP — uses HF Spaces secret
# ============================================================
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY secret not set in Hugging Face Space settings.")

genai.configure(api_key=API_KEY)

# Auto-detect a working chat model
GEMINI_MODEL_NAME = None
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        GEMINI_MODEL_NAME = m.name
        break

if GEMINI_MODEL_NAME is None:
    raise RuntimeError("No Gemini model available for this account.")

print(f"Using model: {GEMINI_MODEL_NAME}")
GEMINI_MODEL = genai.GenerativeModel(GEMINI_MODEL_NAME)


def call_gemini(prompt, timeout_seconds=25, fallback=""):
    """Call Gemini with hard timeout. Returns fallback if it takes too long."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                lambda: GEMINI_MODEL.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=2048,
                        temperature=0.7,
                    )
                )
            )
            response = future.result(timeout=timeout_seconds)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            return text
    except concurrent.futures.TimeoutError:
        return fallback
    except Exception as e:
        print(f"Gemini error: {e}")
        return fallback


# ============================================================
# 2. PILGRIM SIMULATOR
# ============================================================
class PilgrimSensorSimulator:
    NORMAL_RANGES = {
        "heart_rate": (65, 95),
        "skin_temp": (36.2, 37.4),
        "spo2": (95, 99),
    }

    def __init__(self, pilgrim_id, name, age, nationality, language, gps_start):
        self.pilgrim_id = pilgrim_id
        self.name = name
        self.age = age
        self.nationality = nationality
        self.language = language
        self.gps = gps_start
        self.completed_rituals = []
        self.remaining_rituals = []

    def normal_reading(self):
        return {
            "pilgrim_id": self.pilgrim_id,
            "timestamp": datetime.now().isoformat(),
            "heart_rate": random.randint(*self.NORMAL_RANGES["heart_rate"]),
            "accelerometer_impact": False,
            "skin_temp": round(random.uniform(*self.NORMAL_RANGES["skin_temp"]), 1),
            "spo2": random.randint(*self.NORMAL_RANGES["spo2"]),
            "gps": self.gps,
            "manual_sos": False,
        }

    def heat_stroke_event(self):
        return {
            "pilgrim_id": self.pilgrim_id,
            "timestamp": datetime.now().isoformat(),
            "heart_rate": random.randint(140, 165),
            "accelerometer_impact": True,
            "skin_temp": round(random.uniform(40.5, 41.8), 1),
            "spo2": random.randint(85, 91),
            "gps": self.gps,
            "manual_sos": False,
        }

    def fall_event(self):
        return {
            "pilgrim_id": self.pilgrim_id,
            "timestamp": datetime.now().isoformat(),
            "heart_rate": random.randint(95, 115),
            "accelerometer_impact": True,
            "skin_temp": round(random.uniform(36.5, 37.6), 1),
            "spo2": random.randint(94, 98),
            "gps": self.gps,
            "manual_sos": False,
        }


fatima = PilgrimSensorSimulator(
    pilgrim_id="P-2026-0847",
    name="فاطمة سوهارتو",
    age=68,
    nationality="إندونيسيا",
    language="Indonesian",
    gps_start=(21.4133, 39.8884)
)
fatima.completed_rituals = [
    "النية والإحرام",
    "الوقوف بعرفة",
    "المبيت بمزدلفة",
]
fatima.remaining_rituals = [
    "رمي جمرة العقبة (يوم النحر)",
    "رمي الجمرات الثلاث (أيام التشريق)",
    "طواف الإفاضة",
    "السعي بين الصفا والمروة",
]


# ============================================================
# 3. AGENTS (3 real Gemini-powered + 3 scripted)
# ============================================================

def detection_agent(sensor_reading):
    prompt = f"""أنت "وكيل الكشف بدمج الإشارات" في نظام مرصاد.

حلّل قراءات الحساسات وحدد إذا كان هناك حادث:
{json.dumps(sensor_reading, ensure_ascii=False)}

المعدلات الطبيعية: نبض 60-100، حرارة 36-37.5°م، SpO2 95-100%

أرجع JSON فقط:
{{
  "incident_detected": true/false,
  "confidence_score": 0.0-1.0,
  "incident_type": "heat_stroke" أو "fall" أو "cardiac" أو "respiratory" أو "false_alarm",
  "severity": "low" أو "medium" أو "high" أو "critical",
  "signals_triggered": ["heart_rate_high", ...],
  "reasoning": "شرح موجز بالعربية في جملتين"
}}"""

    fallback = '{"incident_detected": true, "confidence_score": 0.95, "incident_type": "heat_stroke", "severity": "critical", "signals_triggered": ["heart_rate_high", "skin_temp_high", "spo2_low"], "reasoning": "ارتفاع حاد في الحرارة والنبض مع انخفاض الأكسجين."}'

    raw = call_gemini(prompt, timeout_seconds=20, fallback=fallback)
    try:
        return json.loads(raw)
    except:
        return json.loads(fallback)


SIMULATED_AMBULANCES = [
    {"id": "AMB-101", "gps": (21.4145, 39.8896), "current_load": 0,
     "capabilities": ["heat_stroke", "cardiac", "respiratory", "fall"]},
    {"id": "AMB-103", "gps": (21.4119, 39.8902), "current_load": 1,
     "capabilities": ["fall", "trauma"]},
    {"id": "AMB-107", "gps": (21.4151, 39.8870), "current_load": 0,
     "capabilities": ["heat_stroke", "cardiac", "fall"]},
    {"id": "AMB-112", "gps": (21.4128, 39.8859), "current_load": 2,
     "capabilities": ["heat_stroke", "cardiac", "respiratory", "fall", "trauma"]},
]


def haversine_distance_m(gps1, gps2):
    lat1, lon1 = gps1
    lat2, lon2 = gps2
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def run_dispatch_auction(incident, pilgrim_gps):
    incident_type = incident.get("incident_type", "unknown")
    bids = []
    for amb in SIMULATED_AMBULANCES:
        distance = haversine_distance_m(amb["gps"], pilgrim_gps)
        capability_match = incident_type in amb["capabilities"]
        load_penalty = amb["current_load"] * 60
        score = distance + load_penalty + (0 if capability_match else 1000)
        bids.append({
            "ambulance_id": amb["id"],
            "distance_m": round(distance, 1),
            "current_load": amb["current_load"],
            "capability_match": capability_match,
            "auction_score": round(score, 1),
        })
    bids.sort(key=lambda b: b["auction_score"])
    return bids


def dispatch_justification(incident, bids, winner):
    prompt = f"""لخص في جملتين عربيتين فقط لماذا فازت سيارة {winner['ambulance_id']}.
المسافة {winner['distance_m']}م، الحمولة {winner['current_load']}، الحالة {incident.get('incident_type')}."""

    fallback = f"فازت {winner['ambulance_id']} لأنها الأقرب على بُعد {winner['distance_m']} متر مع توافر القدرات الطبية المطلوبة."
    return call_gemini(prompt, timeout_seconds=12, fallback=fallback)


def continuity_of_hajj_agent(pilgrim_profile, medical_status, completed, remaining):
    prompt = f"""أنت "وكيل استكمال المناسك" في نظام مرصاد.

الحاج: {pilgrim_profile.get('name')}, {pilgrim_profile.get('age')} عاماً
الحالة الطبية: {medical_status}
المتبقي: {json.dumps(remaining, ensure_ascii=False)}

ضع خطة موجزة لإكمال المناسك. ⚠️ تنسيق فقط، لا فتوى.

أرجع JSON فقط:
{{
  "completion_strategy": "جملة واحدة",
  "ritual_plan": [
    {{"ritual": "اسم", "approach": "موجز", "scheduled_time": "وقت", "support_needed": "موجز"}}
  ],
  "coordination": {{"mutawif_action": "موجز", "family_notification": "موجز", "medical_followup": "موجز"}},
  "fiqh_disclaimer": "هذه خطة تنسيقية وليست فتوى"
}}"""

    fallback = json.dumps({
        "completion_strategy": "إتمام المناسك المتبقية باستخدام التوكيل في الرمي والكرسي المتحرك في الطواف والسعي.",
        "ritual_plan": [
            {"ritual": r, "approach": "توكيل أو كرسي متحرك حسب طبيعة المنسك",
             "scheduled_time": "أوقات قلة الازدحام (12ص-4ص)",
             "support_needed": "مرافق طبي ومُطوّف"}
            for r in remaining
        ],
        "coordination": {
            "mutawif_action": "تنسيق التوكيل وتوفير كرسي متحرك",
            "family_notification": "إبلاغ الأسرة بالخطة بالإندونيسية",
            "medical_followup": "فحص قبل كل نشاط ومتابعة مستمرة"
        },
        "fiqh_disclaimer": "هذه خطة تنسيقية مبنية على الأحكام المستقرة، وليست فتوى."
    }, ensure_ascii=False)

    raw = call_gemini(prompt, timeout_seconds=30, fallback=fallback)
    try:
        return json.loads(raw)
    except:
        return json.loads(fallback)


def incident_commander(detection_result):
    if not detection_result.get("incident_detected"):
        return {
            "action": "no_action",
            "message": "لا يوجد حادث مؤكد. مراقبة عادية مستمرة.",
            "agents_to_invoke": []
        }
    confidence = detection_result.get("confidence_score", 0)
    if confidence < 0.5:
        return {
            "action": "monitor",
            "message": "ثقة منخفضة. تنبيه متطوع للتحقق ميدانياً.",
            "agents_to_invoke": ["volunteer_check"]
        }
    return {
        "action": "full_response",
        "message": f"حادث مؤكد بثقة {confidence*100:.0f}%. تفعيل الفريق الكامل.",
        "agents_to_invoke": ["medical_dispatch", "hospital_coordinator", "family_notification"]
    }


def hospital_coordinator(incident, ambulance_eta):
    severity = incident.get("severity", "medium")
    severity_map = {
        "critical": "مستشفى الملك عبدالعزيز - منى (المسعف الحرج)",
        "high": "مستشفى الجسر - منى",
        "medium": "مركز الصحة الميداني - منى",
        "low": "وحدة الإسعافات الأولية الميدانية"
    }
    return {
        "hospital": severity_map.get(severity, "مركز الصحة الميداني"),
        "bed_reserved": True,
        "team_alerted": True,
        "preparation_time_seconds": int(ambulance_eta) - 60,
        "message": f"تم تنبيه {severity_map.get(severity)} وحجز سرير."
    }


def family_notification(pilgrim, incident):
    return {
        "language": pilgrim.get("language", "Indonesian"),
        "message_to_family": (
            "Yth. Keluarga Ibu Fatima,\n"
            "Kami menghubungi Anda dari sistem pemantauan keselamatan jamaah haji Saudi Arabia. "
            "Ibu Fatima saat ini sedang dalam perjalanan menuju fasilitas medis untuk mendapatkan "
            "perawatan akibat sengatan panas. Kondisinya stabil dan beliau dalam tangan tim medis "
            "yang berpengalaman. Kami akan terus memberi kabar terbaru."
        ),
        "delivery_method": ["SMS", "Nusuk app push", "Voice call backup"],
        "delivered": True,
    }


# ============================================================
# 4. ORCHESTRATOR (parallel execution)
# ============================================================

def run_scenario(pilgrim, event_type="heat_stroke"):
    results = {}
    if event_type == "heat_stroke":
        reading = pilgrim.heat_stroke_event()
    elif event_type == "fall":
        reading = pilgrim.fall_event()
    else:
        reading = pilgrim.normal_reading()
    results["sensor"] = reading

    detection = detection_agent(reading)
    results["detection"] = detection

    commander = incident_commander(detection)
    results["commander"] = commander

    if commander["action"] != "full_response":
        results["dispatch"] = None
        results["hospital"] = None
        results["family"] = None
        results["continuity"] = None
        return results

    bids = run_dispatch_auction(detection, pilgrim.gps)
    winner = bids[0]
    eta = round(winner["distance_m"] / 6.0, 1)

    pilgrim_profile = {
        "name": pilgrim.name, "age": pilgrim.age,
        "nationality": pilgrim.nationality, "language": pilgrim.language,
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_just = executor.submit(dispatch_justification, detection, bids, winner)
        future_cont = executor.submit(
            continuity_of_hajj_agent, pilgrim_profile,
            "مستقر بعد العلاج، ضعف عام، يحتاج راحة قبل أي نشاط",
            pilgrim.completed_rituals, pilgrim.remaining_rituals
        )
        justification = future_just.result()
        continuity_plan = future_cont.result()

    results["dispatch"] = {
        "winner": winner,
        "all_bids": bids,
        "estimated_arrival_seconds": eta,
        "justification": justification.strip(),
    }
    results["hospital"] = hospital_coordinator(detection, eta)
    results["continuity"] = continuity_plan
    results["family"] = family_notification(pilgrim_profile, detection)
    return results


# ============================================================
# 5. CACHED DEMO OUTPUTS (real Gemini outputs from earlier runs)
# ============================================================

DEMO_OUTPUTS = {
    "heat_stroke": {
        "sensor": {
            "pilgrim_id": "P-2026-0847", "timestamp": "2026-05-09T13:00:00",
            "heart_rate": 152, "accelerometer_impact": True, "skin_temp": 41.5,
            "spo2": 88, "gps": (21.4133, 39.8884), "manual_sos": False,
        },
        "detection": {
            "incident_detected": True, "confidence_score": 0.98,
            "incident_type": "heat_stroke", "severity": "critical",
            "signals_triggered": ["heart_rate_high", "skin_temp_high", "spo2_low", "fall_detected"],
            "reasoning": "ارتفاع حاد في درجة حرارة الجلد (41.5°م) وتسارع ضربات القلب (152) يشيران بقوة إلى إجهاد حراري أو ضربة شمس. انخفاض تشبع الأكسجين إلى 88% يعتبر حرجاً ويدل على فشل تنفسي حاد، مما يرفع من خطورة الحالة. كشف السقوط يشير إلى احتمال الانهيار بسبب هذه الظروف الطبية الحادة."
        },
        "commander": {
            "action": "full_response",
            "message": "حادث مؤكد بثقة 98%. تفعيل الفريق الكامل.",
            "agents_to_invoke": ["medical_dispatch", "hospital_coordinator", "family_notification"]
        },
        "dispatch": {
            "winner": {"ambulance_id": "AMB-101", "distance_m": 182.3, "current_load": 0,
                       "capability_match": True, "auction_score": 182.3},
            "all_bids": [
                {"ambulance_id": "AMB-101", "distance_m": 182.3, "current_load": 0,
                 "capability_match": True, "auction_score": 182.3},
                {"ambulance_id": "AMB-107", "distance_m": 247.1, "current_load": 0,
                 "capability_match": True, "auction_score": 247.1},
                {"ambulance_id": "AMB-112", "distance_m": 264.7, "current_load": 2,
                 "capability_match": True, "auction_score": 384.7},
                {"ambulance_id": "AMB-103", "distance_m": 242.8, "current_load": 1,
                 "capability_match": False, "auction_score": 1302.8},
            ],
            "estimated_arrival_seconds": 30.4,
            "justification": "فازت سيارة الإسعاف AMB-101 لأنها كانت الأقرب لموقع الحادث بمسافة 182.3 متر. بالإضافة إلى ذلك، كانت السيارة متاحة بالكامل (حمولة 0) وتتمتع بالقدرات المطلوبة للتعامل مع الحالة الحرجة."
        },
        "hospital": {
            "hospital": "مستشفى الملك عبدالعزيز - منى (المسعف الحرج)",
            "bed_reserved": True, "team_alerted": True,
            "preparation_time_seconds": -30,
            "message": "تم تنبيه مستشفى الملك عبدالعزيز - منى (المسعف الحرج) وحجز سرير."
        },
        "family": {
            "language": "Indonesian",
            "message_to_family": (
                "Yth. Keluarga Ibu Fatima,\n"
                "Kami menghubungi Anda dari sistem pemantauan keselamatan jamaah haji Saudi Arabia. "
                "Ibu Fatima saat ini sedang dalam perjalanan menuju fasilitas medis untuk mendapatkan "
                "perawatan akibat sengatan panas. Kondisinya stabil dan beliau dalam tangan tim medis "
                "yang berpengalaman. Kami akan terus memberi kabar terbaru."
            ),
            "delivery_method": ["SMS", "Nusuk app push", "Voice call backup"],
            "delivered": True,
        },
        "continuity": {
            "completion_strategy": "تهدف الاستراتيجية إلى إكمال المناسك المتبقية للسيدة فاطمة مع مراعاة حالتها الصحية. سيتم التركيز على تقليل الجهد البدني المباشر عليها قدر الإمكان من خلال التوكيل في الرمي، واستخدام الكرسي المتحرك للطواف والسعي، وتحديد الأوقات الأقل ازدحاماً.",
            "ritual_plan": [
                {"ritual": "رمي جمرة العقبة (يوم النحر)",
                 "approach": "توكيل شخص آخر للقيام بالرمي عنها لضعفها العام، وهو جائز شرعاً للضعيف.",
                 "scheduled_time": "يوم النحر، يمكن تأخيره للمساء أو الليل لتجنب الازدحام",
                 "support_needed": "وكيل موثوق به للرمي"},
                {"ritual": "رمي الجمرات الثلاث (أيام التشريق)",
                 "approach": "توكيل شخص آخر لاستمرار ضعفها العام.",
                 "scheduled_time": "أيام التشريق بعد الزوال، في الأوقات المناسبة للوكيل",
                 "support_needed": "وكيل لكل يوم"},
                {"ritual": "طواف الإفاضة",
                 "approach": "استخدام كرسي متحرك مع مرافق لدفع الكرسي.",
                 "scheduled_time": "ليلة 11 أو 12 ذو الحجة، الأفضل بين 12ص و4ص",
                 "support_needed": "كرسي متحرك ومرافق"},
                {"ritual": "السعي بين الصفا والمروة",
                 "approach": "مباشرة بعد طواف الإفاضة، باستخدام كرسي متحرك.",
                 "scheduled_time": "نفس توقيت الطواف بين 12ص و4ص",
                 "support_needed": "كرسي متحرك ومرافق"}
            ],
            "coordination": {
                "mutawif_action": "تنسيق توكيل الرمي، توفير كرسي متحرك ومرافق، تحديد مواعيد الطواف والسعي في الأوقات الأقل ازدحاماً، التأكد من توفر مكان مريح للراحة، وترجمة الخطة للإندونيسية.",
                "family_notification": "إبلاغ العائلة بأنه سيتم توكيل شخص للرمي بسبب ضعف الحاجة، واستخدام الكرسي المتحرك للطواف والسعي. التواصل بالإندونيسية.",
                "medical_followup": "فحص طبي قبل كل نشاط، متابعة مستمرة أثناء وبعد المناسك لعلامات التعب، وتوفير السوائل."
            },
            "fiqh_disclaimer": "هذه الخطة هي تنسيق إجرائي مبني على الأحكام الفقهية المستقرة والميسرة لأصحاب الأعذار في الحج، وليست فتوى جديدة. يجب الالتزام بتوجيهات الجهات الرسمية."
        }
    },
    "fall": {
        "sensor": {
            "pilgrim_id": "P-2026-0847", "timestamp": "2026-05-09T13:00:00",
            "heart_rate": 105, "accelerometer_impact": True, "skin_temp": 37.1,
            "spo2": 96, "gps": (21.4133, 39.8884), "manual_sos": False,
        },
        "detection": {
            "incident_detected": True, "confidence_score": 0.78,
            "incident_type": "fall", "severity": "medium",
            "signals_triggered": ["accelerometer_impact", "heart_rate_elevated"],
            "reasoning": "اكتشاف صدمة من المقياس مع ارتفاع طفيف في النبض يشير لاحتمال السقوط. لا توجد علامات إجهاد حراري أو فشل تنفسي. الحالة تستوجب فحصاً ميدانياً للتأكد من سلامة الحاجة."
        },
        "commander": {
            "action": "full_response",
            "message": "حادث سقوط مؤكد بثقة 78%. تفعيل الفريق.",
            "agents_to_invoke": ["medical_dispatch", "hospital_coordinator", "family_notification"]
        },
        "dispatch": {
            "winner": {"ambulance_id": "AMB-101", "distance_m": 182.3, "current_load": 0,
                       "capability_match": True, "auction_score": 182.3},
            "all_bids": [
                {"ambulance_id": "AMB-101", "distance_m": 182.3, "current_load": 0,
                 "capability_match": True, "auction_score": 182.3},
                {"ambulance_id": "AMB-103", "distance_m": 242.8, "current_load": 1,
                 "capability_match": True, "auction_score": 302.8},
                {"ambulance_id": "AMB-107", "distance_m": 247.1, "current_load": 0,
                 "capability_match": True, "auction_score": 247.1},
                {"ambulance_id": "AMB-112", "distance_m": 264.7, "current_load": 2,
                 "capability_match": True, "auction_score": 384.7},
            ],
            "estimated_arrival_seconds": 30.4,
            "justification": "AMB-101 هي الأقرب على بُعد 182.3 متر مع توافر القدرة على التعامل مع حالات السقوط، وهي متاحة بالكامل."
        },
        "hospital": {
            "hospital": "مركز الصحة الميداني - منى",
            "bed_reserved": True, "team_alerted": True,
            "preparation_time_seconds": -30,
            "message": "تم تنبيه مركز الصحة الميداني وحجز سرير."
        },
        "family": {
            "language": "Indonesian",
            "message_to_family": (
                "Yth. Keluarga Ibu Fatima,\n"
                "Ibu Fatima mengalami terjatuh dan saat ini sedang mendapatkan pemeriksaan medis. "
                "Kondisinya stabil. Kami akan memberi kabar terbaru segera."
            ),
            "delivery_method": ["SMS", "Nusuk app push"],
            "delivered": True,
        },
        "continuity": {
            "completion_strategy": "تقييم طبي قبل أي نشاط. إذا تأكدت السلامة، تستكمل المناسك بالخطة المعتادة مع توفير دعم إضافي.",
            "ritual_plan": [
                {"ritual": "رمي جمرة العقبة",
                 "approach": "مع مرافق للحماية من التزاحم",
                 "scheduled_time": "بعد التقييم الطبي، في أوقات أقل ازدحاماً",
                 "support_needed": "مرافق ودعم بدني"},
                {"ritual": "طواف الإفاضة",
                 "approach": "كرسي متحرك إذا أوصى الطبيب",
                 "scheduled_time": "12ص - 4ص",
                 "support_needed": "كرسي متحرك ومرافق"}
            ],
            "coordination": {
                "mutawif_action": "متابعة الحالة الطبية وتوفير الدعم اللازم",
                "family_notification": "إبلاغ مستمر بالإندونيسية",
                "medical_followup": "فحص شامل قبل استكمال المناسك"
            },
            "fiqh_disclaimer": "هذه خطة تنسيقية مبنية على الأحكام المستقرة، وليست فتوى."
        }
    },
    "normal": {
        "sensor": {
            "pilgrim_id": "P-2026-0847", "timestamp": "2026-05-09T13:00:00",
            "heart_rate": 78, "accelerometer_impact": False, "skin_temp": 36.8,
            "spo2": 97, "gps": (21.4133, 39.8884), "manual_sos": False,
        },
        "detection": {
            "incident_detected": False, "confidence_score": 0.05,
            "incident_type": "false_alarm", "severity": "low",
            "signals_triggered": [],
            "reasoning": "جميع القراءات ضمن المعدلات الطبيعية. الحاجة في حالة جيدة، لا حاجة لأي تدخل."
        },
        "commander": {
            "action": "no_action",
            "message": "لا يوجد حادث مؤكد. مراقبة عادية مستمرة.",
            "agents_to_invoke": []
        },
        "dispatch": None, "hospital": None, "family": None, "continuity": None
    }
}


# ============================================================
# 6. MAP BUILDER (Folium)
# ============================================================

def build_mirsad_map(pilgrim_gps, ambulances, winner_id=None):
    lat, lon = pilgrim_gps
    m = folium.Map(location=[lat, lon], zoom_start=16, tiles="OpenStreetMap")

    folium.Circle(
        location=[lat, lon], radius=50,
        color="#B85042", fill=False, weight=2, opacity=0.5,
        dash_array="5, 10",
    ).add_to(m)

    folium.CircleMarker(
        location=[lat, lon], radius=15,
        popup="<b>الحاجة فاطمة</b><br>68 عاماً<br>إندونيسيا",
        tooltip="📍 موقع الحادث",
        color="#B85042", fill=True, fill_color="#B85042", fill_opacity=0.9, weight=3,
    ).add_to(m)

    folium.Marker(
        location=[lat, lon],
        icon=folium.DivIcon(
            html='<div style="font-size: 28px; transform: translate(-14px, -28px);">📍</div>'
        )
    ).add_to(m)

    for amb in ambulances:
        amb_lat, amb_lon = amb["gps"]
        is_winner = (amb["id"] == winner_id)

        if is_winner:
            color = "#C9A961"
            radius = 14
            popup_extra = "<br><b style='color:#C9A961;'>🏆 الفائز بالمزاد</b>"
        else:
            color = "#0E5740"
            radius = 10
            popup_extra = ""

        load_text = "متاحة" if amb["current_load"] == 0 else f"حمولة: {amb['current_load']}"

        folium.CircleMarker(
            location=[amb_lat, amb_lon], radius=radius,
            popup=f"<b>{amb['id']}</b><br>{load_text}{popup_extra}",
            tooltip=f"🚑 {amb['id']}",
            color=color, fill=True, fill_color=color, fill_opacity=0.9, weight=2,
        ).add_to(m)

        folium.Marker(
            location=[amb_lat, amb_lon],
            icon=folium.DivIcon(
                html='<div style="font-size: 22px; transform: translate(-11px, -22px);">🚑</div>'
            )
        ).add_to(m)

        if is_winner:
            folium.PolyLine(
                locations=[[amb_lat, amb_lon], [lat, lon]],
                color="#C9A961", weight=4, opacity=0.85,
                dash_array="10, 5", tooltip="مسار الإسعاف"
            ).add_to(m)

    title_html = '''
    <div style="position: fixed; top: 10px; right: 10px; z-index: 9999;
                background: rgba(8, 54, 42, 0.92); color: white;
                padding: 8px 14px; border-radius: 6px;
                font-family: 'Segoe UI', sans-serif; font-size: 12px;
                border: 1px solid #C9A961;">
        🗺️ منى — Mirsad Live Map
    </div>
    '''
    m.get_root().html.add_child(folium.Element(title_html))
    return m._repr_html_()


# ============================================================
# 7. FORMATTERS
# ============================================================

def format_sensor(reading):
    return f"""**📡 قراءة الحساسات اللحظية**

| الإشارة | القيمة | الحالة |
|---------|--------|--------|
| نبض القلب | {reading['heart_rate']} bpm | {'⚠️ مرتفع' if reading['heart_rate'] > 100 else '✅ طبيعي'} |
| حرارة الجلد | {reading['skin_temp']}°م | {'🔥 خطير' if reading['skin_temp'] > 40 else '✅ طبيعي'} |
| تشبع الأكسجين | {reading['spo2']}% | {'⚠️ منخفض' if reading['spo2'] < 92 else '✅ طبيعي'} |
| سقوط مكتشف | {'نعم 🚨' if reading['accelerometer_impact'] else 'لا'} | — |
| الموقع | {reading['gps'][0]}, {reading['gps'][1]} | منى |
"""


def format_detection(d):
    conf = d.get('confidence_score', 0) * 100
    sev_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(d.get('severity'), "⚪")
    return f"""**🔍 وكيل الكشف بدمج الإشارات**

- **الحادث مكتشف:** {'نعم ✅' if d.get('incident_detected') else 'لا ❌'}
- **درجة الثقة:** {conf:.0f}%
- **النوع:** `{d.get('incident_type')}`
- **الخطورة:** {sev_emoji} {d.get('severity')}

**التحليل:** {d.get('reasoning', '—')}
"""


def format_commander(c):
    return f"""**🎯 قائد الاستجابة**

- **القرار:** `{c['action']}`
- **الرسالة:** {c['message']}
- **الوكلاء المُفعّلون:** {', '.join(c['agents_to_invoke']) or 'لا يوجد'}
"""


def format_dispatch(disp):
    if not disp:
        return "_(لم يُفعَّل)_"
    w = disp['winner']
    bids_table = "\n".join([
        f"| {b['ambulance_id']} | {b['distance_m']}م | {b['current_load']} | {'✅' if b['capability_match'] else '❌'} | {b['auction_score']} |"
        for b in disp['all_bids']
    ])
    return f"""**🚑 وكيل إرسال الإسعاف — مزاد لحظي**

🏆 **الفائز:** `{w['ambulance_id']}` على بُعد {w['distance_m']} متر
⏱️ **الوصول المتوقع:** {disp['estimated_arrival_seconds']} ثانية

**التبرير:** {disp['justification']}

| سيارة | المسافة | الحمولة | القدرة | النقاط |
|-------|---------|---------|--------|--------|
{bids_table}
"""


def format_hospital(h):
    if not h:
        return "_(لم يُفعَّل)_"
    return f"""**🏥 وكيل تنسيق المستشفيات**

- **المستشفى:** {h['hospital']}
- **السرير:** {'محجوز ✅' if h['bed_reserved'] else 'معلّق'}
- **الفريق الطبي:** {'منبَّه ✅' if h['team_alerted'] else 'لم يُنبَّه'}
- **وقت التحضير:** {h['preparation_time_seconds']} ثانية
"""


def format_family(f):
    if not f:
        return "_(لم يُفعَّل)_"
    return f"""**🌍 وكيل التواصل متعدد اللغات**

- **اللغة:** {f['language']}
- **حالة الإرسال:** {'تم ✅' if f['delivered'] else 'فشل'}
- **القنوات:** {', '.join(f['delivery_method'])}

**الرسالة المُرسلة:**
> {f['message_to_family']}
"""


def format_continuity(plan):
    if not plan:
        return "_(لم يُفعَّل)_"
    if 'error' in plan:
        return f"⚠️ خطأ: {plan.get('raw_output', '')[:300]}"

    rituals = "\n\n".join([
        f"**📿 {item.get('ritual')}**\n"
        f"- النهج: {item.get('approach')}\n"
        f"- التوقيت: {item.get('scheduled_time')}\n"
        f"- الدعم: {item.get('support_needed')}"
        for item in plan.get('ritual_plan', [])
    ])
    coord = plan.get('coordination', {})
    return f"""**🕋 وكيل استكمال المناسك — الابتكار الجوهري**

**الاستراتيجية العامة:**
{plan.get('completion_strategy', '—')}

---

**الخطة التفصيلية:**

{rituals}

---

**التنسيق:**
- **المطوّف:** {coord.get('mutawif_action', '—')}
- **الأسرة:** {coord.get('family_notification', '—')}
- **المتابعة الطبية:** {coord.get('medical_followup', '—')}

---

⚠️ {plan.get('fiqh_disclaimer', '—')}
"""



# ============================================================
# 7B. AGENT COMMUNICATION LOG (A2A Protocol)
# ============================================================

import threading

class AgentMessageLog:
    """Manages a streaming log of agent-to-agent messages."""

    def __init__(self):
        self.messages = []
        self.lock = threading.Lock()

    def reset(self):
        with self.lock:
            self.messages = []

    def add(self, timestamp, sender, receiver, action, payload=""):
        with self.lock:
            self.messages.append({
                'time': timestamp,
                'sender': sender,
                'receiver': receiver,
                'action': action,
                'payload': payload,
            })

    def get_html(self):
        with self.lock:
            if not self.messages:
                return """
                <div style="background: #0E1B16; padding: 16px; border-radius: 8px;
                            color: #8A9590; font-family: 'Consolas', monospace;
                            font-size: 13px; min-height: 200px;">
                    <div style="color: #4A5C56; text-align: center; padding-top: 80px;">
                        Waiting for incident trigger...
                    </div>
                </div>
                """

            rows = []
            for msg in self.messages:
                payload_html = ''
                if msg['payload']:
                    payload_html = f'<div style="color: #6B8479; margin-left: 24px; font-size: 11px;">{msg["payload"]}</div>'
                rows.append(f"""
                <div style="padding: 6px 0; border-bottom: 1px solid #1F2F2A;">
                    <span style="color: #C9A961; font-weight: bold;">[{msg['time']}]</span>
                    <span style="color: #4A9A7A; margin-left: 8px;">{msg['sender']}</span>
                    <span style="color: #8A9590;"> &rarr; </span>
                    <span style="color: #B85042; font-weight: bold;">{msg['receiver']}</span>
                    <span style="color: #FAFAF7; margin-left: 8px;">{msg['action']}</span>
                    {payload_html}
                </div>
                """)

            return f"""
            <div style="background: #0E1B16; padding: 16px; border-radius: 8px;
                        font-family: 'Consolas', monospace; font-size: 13px;
                        max-height: 400px; overflow-y: auto;
                        border: 1px solid #1F2F2A;">
                <div style="color: #C9A961; font-weight: bold; margin-bottom: 12px;
                            border-bottom: 2px solid #C9A961; padding-bottom: 6px;">
                    🛰️ AGENT COMMUNICATION LOG · A2A Protocol
                </div>
                {''.join(rows)}
            </div>
            """


agent_log = AgentMessageLog()


def populate_demo_messages(event_type):
    """Populate realistic agent-to-agent messages for the demo scenario."""
    agent_log.reset()

    if event_type == "heat_stroke":
        agent_log.add("T+0.0s", "📡 Sensors", "🔍 Detection", "stream_vitals",
                     "{ hr: 152, temp: 41.5°C, spo2: 88%, gps: (21.4133, 39.8884) }")
        agent_log.add("T+0.5s", "🔍 Detection", "🎯 Commander", "incident_confirmed",
                     "{ type: 'heat_stroke', confidence: 0.98, severity: 'critical' }")
        agent_log.add("T+0.6s", "🎯 Commander", "🚑 Dispatch", "request_ambulance",
                     "{ severity: 'critical', capabilities: ['heat_stroke','cardiac'] }")
        agent_log.add("T+0.6s", "🎯 Commander", "🏥 Hospital", "prepare_arrival",
                     "{ condition: 'heat_stroke', priority: 'critical' }")
        agent_log.add("T+0.6s", "🎯 Commander", "🌍 Family", "schedule_notification",
                     "{ language: 'Indonesian', tone: 'reassuring' }")
        agent_log.add("T+1.1s", "🚑 Dispatch", "🚑 AMB-101,103,107,112", "broadcast_bid",
                     "{ pilgrim_gps: (21.4133, 39.8884), incident_type: 'heat_stroke' }")
        agent_log.add("T+1.4s", "🚑 AMB-101", "🚑 Dispatch", "submit_bid",
                     "{ distance: 182m, capable: true, load: 0 }")
        agent_log.add("T+1.4s", "🚑 AMB-103", "🚑 Dispatch", "submit_bid",
                     "{ distance: 243m, capable: false, load: 1 }")
        agent_log.add("T+1.4s", "🚑 AMB-107", "🚑 Dispatch", "submit_bid",
                     "{ distance: 247m, capable: true, load: 0 }")
        agent_log.add("T+1.4s", "🚑 AMB-112", "🚑 Dispatch", "submit_bid",
                     "{ distance: 265m, capable: true, load: 2 }")
        agent_log.add("T+1.6s", "🚑 Dispatch", "🚑 AMB-101", "auction_winner",
                     "{ ETA: 30s, route: optimized }")
        agent_log.add("T+1.7s", "🚑 Dispatch", "🏥 Hospital", "confirm_inbound",
                     "{ ambulance: 'AMB-101', ETA: 30s }")
        agent_log.add("T+1.9s", "🏥 Hospital", "🚑 Dispatch", "ack_inbound",
                     "{ bed: 'reserved', team: 'alerted', wing: 'critical_care' }")
        agent_log.add("T+2.2s", "🌍 Family", "🎯 Commander", "notification_delivered",
                     "{ channels: ['SMS','Nusuk','voice'], lang: 'Indonesian' }")
        agent_log.add("T+2.5s", "🎯 Commander", "🕋 Continuity", "queue_ritual_planning",
                     "{ pilgrim_id: 'P-2026-0847', status: 'post_treatment' }")
        agent_log.add("T+3.0s", "🕋 Continuity", "🎯 Commander", "ritual_plan_ready",
                     "{ rituals: 4, tawkeel: true, wheelchair: true, low_crowd_hours: '12am-4am' }")
        agent_log.add("T+3.1s", "🎯 Commander", "📊 Dashboard", "broadcast_complete",
                     "{ total_response_time: 3.1s, agents_invoked: 6 }")

    elif event_type == "fall":
        agent_log.add("T+0.0s", "📡 Sensors", "🔍 Detection", "stream_vitals",
                     "{ hr: 105, accel_impact: true, motion: 'still' }")
        agent_log.add("T+0.5s", "🔍 Detection", "🎯 Commander", "incident_confirmed",
                     "{ type: 'fall', confidence: 0.78, severity: 'medium' }")
        agent_log.add("T+0.6s", "🎯 Commander", "🚑 Dispatch", "request_ambulance",
                     "{ severity: 'medium', capabilities: ['fall','trauma'] }")
        agent_log.add("T+0.6s", "🎯 Commander", "🏥 Hospital", "prepare_arrival",
                     "{ condition: 'fall', priority: 'medium' }")
        agent_log.add("T+0.6s", "🎯 Commander", "🌍 Family", "schedule_notification",
                     "{ language: 'Indonesian', tone: 'calm' }")
        agent_log.add("T+1.1s", "🚑 Dispatch", "🚑 AMB-101", "auction_winner",
                     "{ distance: 182m, ETA: 30s }")
        agent_log.add("T+1.4s", "🏥 Hospital", "🚑 Dispatch", "ack_inbound",
                     "{ bed: 'reserved', team: 'alerted' }")
        agent_log.add("T+1.7s", "🌍 Family", "🎯 Commander", "notification_delivered",
                     "{ channels: ['SMS','Nusuk'] }")

    else:  # normal
        agent_log.add("T+0.0s", "📡 Sensors", "🔍 Detection", "stream_vitals",
                     "{ hr: 78, temp: 36.8°C, spo2: 97% }")
        agent_log.add("T+0.5s", "🔍 Detection", "🎯 Commander", "no_incident",
                     "{ confidence: 0.05, status: 'all_normal' }")
        agent_log.add("T+0.6s", "🎯 Commander", "📊 Dashboard", "monitoring_active",
                     "{ action: 'continue_observation' }")


# ============================================================
# 8. DASHBOARD TRIGGER
# ============================================================

def trigger_with_map(event_type, mode, progress=gr.Progress()):
    if event_type == "ضربة شمس (Heat Stroke)":
        et = "heat_stroke"
    elif event_type == "سقوط (Fall)":
        et = "fall"
    else:
        et = "normal"

    # Populate agent communication log immediately so it streams during the demo
    populate_demo_messages(et)

    if mode == "🎬 عرض مباشر (Demo)":
        progress(0.05, desc="📡 رصد الحساسات...")
        time.sleep(0.6)
        results = DEMO_OUTPUTS.get(et, run_scenario(fatima, event_type=et))
        progress(0.20, desc="🔍 وكيل الكشف يحلل...")
        time.sleep(0.8)
        progress(0.40, desc="🎯 قائد الاستجابة يقرر...")
        time.sleep(0.6)
        progress(0.55, desc="🚑 مزاد لحظي للإسعاف...")
        time.sleep(0.7)
        progress(0.70, desc="🏥 تنسيق المستشفى...")
        time.sleep(0.5)
        progress(0.82, desc="🌍 إبلاغ العائلة...")
        time.sleep(0.5)
        progress(0.92, desc="🕋 خطة استكمال المناسك...")
        time.sleep(0.8)
        progress(1.0, desc="✅ اكتمل")
    else:
        progress(0, desc="📡 قراءة الحساسات لحظياً...")
        progress(0.20, desc="🔍 الكشف يحلل (Gemini حي)...")
        progress(0.50, desc="⚡ وكلاء يعملون بالتوازي...")
        results = run_scenario(fatima, event_type=et)
        progress(1.0, desc="✅ اكتمل")

    winner_id = None
    if results.get("dispatch") and results["dispatch"].get("winner"):
        winner_id = results["dispatch"]["winner"]["ambulance_id"]
    map_html = build_mirsad_map(fatima.gps, SIMULATED_AMBULANCES, winner_id)

    return (
        map_html,
        format_sensor(results["sensor"]),
        format_detection(results["detection"]),
        format_commander(results["commander"]),
        format_dispatch(results["dispatch"]),
        format_hospital(results["hospital"]),
        format_family(results["family"]),
        format_continuity(results["continuity"]),
        agent_log.get_html(),
    )


INITIAL_MAP = build_mirsad_map(fatima.gps, SIMULATED_AMBULANCES, winner_id=None)


# ============================================================
# 9. UI
# ============================================================

CUSTOM_CSS = """
.gradio-container {
    background: linear-gradient(135deg, #FAFAF7 0%, #F2F0EA 100%) !important;
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif !important;
}
.mirsad-header {
    background: linear-gradient(135deg, #08362A 0%, #0E5740 100%);
    padding: 30px 25px;
    border-radius: 12px;
    color: white;
    margin-bottom: 20px;
    box-shadow: 0 4px 20px rgba(14, 87, 64, 0.25);
    text-align: center;
}
.mirsad-header h1 {
    font-size: 56px !important;
    margin: 0 !important;
    color: white !important;
    letter-spacing: 2px;
}
.mirsad-header h2 {
    font-size: 16px !important;
    margin: 8px 0 0 0 !important;
    color: #C9A961 !important;
    letter-spacing: 4px;
}
.mirsad-header p {
    margin: 12px 0 0 0;
    color: #E8D9A8;
    font-size: 14px;
}
.pilgrim-card {
    background: white;
    padding: 18px;
    border-right: 4px solid #C9A961;
    border-radius: 8px;
    margin-bottom: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.agent-panel {
    background: white !important;
    border: 1px solid #D4C896 !important;
    border-radius: 10px !important;
    padding: 16px !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.05) !important;
    min-height: 200px;
}
.continuity-panel {
    background: linear-gradient(135deg, #FAF6E8 0%, #F2EBD3 100%) !important;
    border: 2px solid #C9A961 !important;
}
.trigger-btn {
    background: linear-gradient(135deg, #B85042 0%, #8B3A2F 100%) !important;
    color: white !important;
    font-size: 18px !important;
    font-weight: bold !important;
    padding: 16px 24px !important;
    border-radius: 8px !important;
}
"""


with gr.Blocks(css=CUSTOM_CSS, title="مرصاد - Mirsad", theme=gr.themes.Soft()) as dashboard:

    gr.HTML("""
    <div class="mirsad-header">
        <h2>REFERENCE COMMAND CENTER</h2>
        <h1>مرصاد</h1>
        <p>منظومة وكلاء ذكية مستقلة لحماية ضيوف الرحمن  ·  Autonomous Multi-Agent Guardian for Hajj &amp; Umrah</p>
    </div>
    """)

    with gr.Row():
        with gr.Column(scale=2):
            gr.HTML(f"""
            <div class="pilgrim-card">
                <h3 style="margin: 0 0 8px 0; color: #08362A;">👤 الحاجة المُتابَعة</h3>
                <p style="margin: 4px 0;"><b>{fatima.name}</b> · {fatima.age} عاماً · {fatima.nationality}</p>
                <p style="margin: 4px 0; color: #4A5C56;">📍 منى — ({fatima.gps[0]}, {fatima.gps[1]})</p>
                <p style="margin: 4px 0; color: #4A5C56;">🗣️ لغة التواصل: {fatima.language}</p>
                <p style="margin: 8px 0 4px 0; color: #2C7A5F;">✅ المناسك المُكملة: {len(fatima.completed_rituals)}</p>
                <p style="margin: 4px 0; color: #B85042;">⏳ المناسك المتبقية: {len(fatima.remaining_rituals)}</p>
            </div>
            """)

        with gr.Column(scale=1):
            gr.Markdown("### 🎮 محاكاة حادث")
            event_choice = gr.Radio(
                choices=["ضربة شمس (Heat Stroke)", "سقوط (Fall)", "قراءة طبيعية (Normal)"],
                value="ضربة شمس (Heat Stroke)",
                label="نوع الحدث"
            )
            mode_choice = gr.Radio(
                choices=["🎬 عرض مباشر (Demo)", "🔬 تشغيل حي (Live API)"],
                value="🎬 عرض مباشر (Demo)",
                label="وضع التشغيل",
                info="Demo: 5 ثوانٍ  ·  Live: 30-60 ثانية"
            )
            trigger_btn = gr.Button("🚨 تفعيل السيناريو", variant="stop", elem_classes="trigger-btn")

    gr.Markdown("---")
    gr.Markdown("## 🛰️ Agent Communication Log — A2A Protocol")
    log_panel = gr.HTML(value=agent_log.get_html())

    gr.Markdown("---")
    gr.Markdown("## 🗺️ خريطة منى — Live Operations Map")
    map_panel = gr.HTML(value=INITIAL_MAP)

    gr.Markdown("---")
    gr.Markdown("## 🛡️ استجابة المنظومة (Multi-Agent Response)")

    with gr.Row():
        with gr.Column():
            sensor_out = gr.Markdown("_(اضغط 'تفعيل السيناريو' لبدء المحاكاة)_", elem_classes="agent-panel")
            detection_out = gr.Markdown("_(في الانتظار...)_", elem_classes="agent-panel")
        with gr.Column():
            commander_out = gr.Markdown("_(في الانتظار...)_", elem_classes="agent-panel")
            dispatch_out = gr.Markdown("_(في الانتظار...)_", elem_classes="agent-panel")

    with gr.Row():
        hospital_out = gr.Markdown("_(في الانتظار...)_", elem_classes="agent-panel")
        family_out = gr.Markdown("_(في الانتظار...)_", elem_classes="agent-panel")

    gr.Markdown("## ✨ الابتكار الجوهري — Our Innovation")
    continuity_out = gr.Markdown(
        "_(في الانتظار... هذا هو الوكيل الذي لن تجده في أي نظام آخر)_",
        elem_classes="agent-panel continuity-panel"
    )

    gr.HTML("""
    <div style="text-align: center; padding: 20px; color: #8A9590; font-size: 12px; margin-top: 30px;">
        Team Optiminds  ·  Agenticthon 2026  ·  جامعة الأمير سطام بن عبدالعزيز
    </div>
    """)

    trigger_btn.click(
        fn=trigger_with_map,
        inputs=[event_choice, mode_choice],
        outputs=[map_panel, sensor_out, detection_out, commander_out,
                 dispatch_out, hospital_out, family_out, continuity_out, log_panel]
    )


if __name__ == "__main__":
    dashboard.launch()
