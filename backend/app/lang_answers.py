"""Built-in (no-AI) answer sentences per language. lang.localize() matches the English sentence the planner wrote
and rebuilds it from these templates. A missing key falls back to the English template.

Other languages are in lang_answers_tr.py (same keys). Keep placeholders identical; order may change.
"""
ANS: dict[str, dict[str, str]] = {
    "en": {
        "end": ".",
        "place_home": "Home", "place_school": "School", "place_tuition": "Tuition",
        "today": "today", "yesterday": "yesterday",
        "just_now": "just now", "ago_min": "{n} min ago", "ago_h": "{n} h ago", "ago_d": "{n} d ago",
        "moving": ", moving at {s} km/h",
        "status_known": "📍 {l} is at {p}{mv} (updated {t}, {fresh}).",
        "status_near": "📍 {l} is near {n}{mv} (updated {t}, {fresh}).",
        "status_unknown": "📍 {l} is at a place not in the routine{mv} (updated {t}, {fresh}).",
        "usual_here": " ✅ That's where {l} usually is at this time.",
        "usual_other": " Note: usually {l} is at {p} at this time.",
        "trip": "🚶 Left {f} at {t} · {k} km so far",
        "trip_heading": " · heading to {d}, expected ~{e} ({n} min)",
        "on_way_live": "🚶 {l} left {f} at {t} and is on the way to {d} – about {k} km left. "
                       "Expected around {e} (~{n} min, estimate from today's speed).",
        "battery": "🔋 Battery {b}%",
        "no_sos": "✅ No SOS.",
        "sos_active": "🚨 SOS ACTIVE – open the SOS screen.",
        "reached_still": "✅ {l} reached {p} at {t} {day} and is still there.",
        "reached_left": "✅ {l} reached {p} at {t} {day} and left around {left}.",
        "not_there_n": "❗ {l} has not been at {p} {day} ({n} tracker reports that day).",
        "not_there_none": "❗ {l} has not been at {p} {day} – no tracker data.",
        "already": "🏠 {l} is already at {p} (updated {t}).",
        "on_way": "🚶 {l} is on the way to {p}. Expected at {t} (about {n} min, {k} km left).",
        "usual_trip": " Usually this trip takes {u} min.",
        "offline": "⚠️ The tracker is OFFLINE – no update for {a}, so this is not live.",
        "call_check": "Please call or check the tracker is charged and switched on.",
        "no_report": "No report from {l}'s tracker yet.",
        "emergency": "🚨 If you think {l} is in danger, call 112 now. In the app: open {l}'s SOS / map screen → "
                     "Navigate, share the live link, or press Emergency – School / Emergency – Group (Smart plan) "
                     "so nearby people can help.",
        "crisis": "I'm sorry you're going through this. If anyone is in immediate danger, call 112 now. For support "
                  "you can call Tele-MANAS on 14416 (free, 24×7) or the Childline on 1098. You're not alone – please "
                  "reach out to someone you trust.",
        "out_of_scope": "Sorry, that's out of scope – I can only answer questions about {l}'s tracker (location, "
                        "arrivals, trips, alerts, battery). Try: “Where is {l} now?”, “Did {l} reach school?”",
    },
    "hi": {
        "end": "।",
        "place_home": "घर", "place_school": "स्कूल", "place_tuition": "ट्यूशन",
        "today": "आज", "yesterday": "कल",
        "just_now": "अभी-अभी", "ago_min": "{n} मिनट पहले", "ago_h": "{n} घंटे पहले", "ago_d": "{n} दिन पहले",
        "moving": ", {s} km/h की रफ़्तार से चल रहा है",
        "status_known": "📍 {l} {p} पर है{mv} ({t} बजे अपडेट, {fresh})।",
        "status_near": "📍 {l} {n} के पास है{mv} ({t} बजे अपडेट, {fresh})।",
        "status_unknown": "📍 {l} किसी ऐसी जगह पर है जो रूटीन में नहीं है{mv} ({t} बजे अपडेट, {fresh})।",
        "usual_here": " ✅ इस समय की यही सामान्य जगह है।",
        "usual_other": " ध्यान दें: इस समय की सामान्य जगह {p} है।",
        "trip": "🚶 {t} बजे {f} से निकले · अब तक {k} km",
        "trip_heading": " · {d} की ओर, लगभग {e} बजे तक पहुँचने का अनुमान ({n} मिनट)",
        "on_way_live": "🚶 {l} {t} बजे {f} से निकले और {d} के रास्ते में हैं – लगभग {k} km बाकी। "
                       "लगभग {e} बजे तक पहुँचने का अनुमान है (~{n} मिनट, आज की रफ़्तार के हिसाब से)।",
        "battery": "🔋 बैटरी {b}%",
        "no_sos": "✅ कोई SOS नहीं।",
        "sos_active": "🚨 SOS चालू है – SOS स्क्रीन खोलें।",
        "reached_still": "✅ {day} {t} बजे {l} के {p} पहुँचने का रिकॉर्ड है। {l} अभी भी वहीं है।",
        "reached_left": "✅ {day} {t} बजे {l} के {p} पहुँचने का रिकॉर्ड है। लगभग {left} बजे वहाँ से निकलना दर्ज हुआ।",
        "not_there_n": "❗ {day} {l} के {p} पर होने का कोई रिकॉर्ड नहीं है (उस दिन ट्रैकर की {n} रिपोर्ट)।",
        "not_there_none": "❗ {day} {l} के {p} पर होने का कोई रिकॉर्ड नहीं है (ट्रैकर का कोई डेटा नहीं)।",
        "already": "🏠 {l} पहले से {p} पर है ({t} बजे अपडेट)।",
        "on_way": "🚶 {l} {p} के रास्ते में है। लगभग {t} बजे तक पहुँचने की उम्मीद है (करीब {n} मिनट, {k} km बाकी)।",
        "usual_trip": " आमतौर पर यह सफ़र {u} मिनट का होता है।",
        "offline": "⚠️ ट्रैकर ऑफ़लाइन है – {a} से कोई अपडेट नहीं, इसलिए यह लाइव लोकेशन नहीं है।",
        "call_check": "कृपया फ़ोन करें या देखें कि ट्रैकर चार्ज और चालू है।",
        "no_report": "{l} के ट्रैकर से अभी तक कोई रिपोर्ट नहीं आई है।",
        "emergency": "🚨 अगर आपको लगता है कि {l} खतरे में है, तो अभी 112 पर कॉल करें। ऐप में: {l} की SOS / मैप स्क्रीन खोलें "
                     "→ रास्ता देखें, लाइव लिंक शेयर करें, या इमरजेंसी – स्कूल / इमरजेंसी – ग्रुप दबाएँ ताकि आस-पास के लोग "
                     "मदद कर सकें।",
        "crisis": "मुझे खेद है कि आप इससे गुज़र रहे हैं। अगर कोई तुरंत खतरे में है, तो अभी 112 पर कॉल करें। सहायता के लिए "
                  "Tele-MANAS 14416 (मुफ़्त, 24×7) या Childline 1098 पर कॉल करें। आप अकेले नहीं हैं।",
        "out_of_scope": "माफ़ कीजिए, मैं सिर्फ़ {l} के ट्रैकर के बारे में बता सकता हूँ (लोकेशन, पहुँचना, सफ़र, अलर्ट, बैटरी)। "
                        "जैसे: “{l} अभी कहाँ है?”, “{l} स्कूल कब पहुँचा?”",
    },
    "bn": {
        "end": "।",
        "place_home": "বাড়ি", "place_school": "স্কুল", "place_tuition": "টিউশন",
        "today": "আজ", "yesterday": "গতকাল",
        "just_now": "এইমাত্র", "ago_min": "{n} মিনিট আগে", "ago_h": "{n} ঘণ্টা আগে", "ago_d": "{n} দিন আগে",
        "moving": ", {s} km/h গতিতে চলছে",
        "status_known": "📍 {l} {p}-এ আছে{mv} ({t}-এ আপডেট, {fresh})।",
        "status_near": "📍 {l} {n}-এর কাছে আছে{mv} ({t}-এ আপডেট, {fresh})।",
        "status_unknown": "📍 {l} রুটিনের বাইরে একটি জায়গায় আছে{mv} ({t}-এ আপডেট, {fresh})।",
        "usual_here": " ✅ এই সময়ে {l} সাধারণত এখানেই থাকে।",
        "usual_other": " লক্ষ্য করুন: এই সময়ে {l} সাধারণত {p}-এ থাকে।",
        "trip": "🚶 {t}-এ {f} থেকে বেরিয়েছে · এ পর্যন্ত {k} km",
        "trip_heading": " · {d}-এর দিকে যাচ্ছে, আনুমানিক {e}-এ পৌঁছাবে ({n} মিনিট)",
        "on_way_live": "🚶 {l} {t}-এ {f} থেকে বেরিয়ে {d}-এর পথে আছে – প্রায় {k} km বাকি। "
                       "আনুমানিক {e}-এ পৌঁছাবে (~{n} মিনিট, আজকের গতি অনুযায়ী)।",
        "battery": "🔋 ব্যাটারি {b}%",
        "no_sos": "✅ কোনো SOS নেই।",
        "sos_active": "🚨 SOS চালু আছে – SOS স্ক্রিন খুলুন।",
        "reached_still": "✅ {l} {day} {t}-এ {p}-এ পৌঁছেছে এবং এখনও সেখানেই আছে।",
        "reached_left": "✅ {l} {day} {t}-এ {p}-এ পৌঁছেছে এবং প্রায় {left}-এ বেরিয়ে গেছে।",
        "not_there_n": "❗ {day} {l} {p}-এ যায়নি (সেদিন ট্র্যাকারের {n}টি রিপোর্ট)।",
        "not_there_none": "❗ {day} {l} {p}-এ যায়নি (কোনো ট্র্যাকার ডেটা নেই)।",
        "already": "🏠 {l} ইতিমধ্যে {p}-এ আছে ({t}-এ আপডেট)।",
        "on_way": "🚶 {l} {p}-এর পথে আছে। আনুমানিক {t}-এ পৌঁছাবে (প্রায় {n} মিনিট, {k} km বাকি)।",
        "usual_trip": " সাধারণত এই যাত্রায় {u} মিনিট লাগে।",
        "offline": "⚠️ ট্র্যাকার অফলাইন – {a} ধরে কোনো আপডেট নেই, তাই এটি লাইভ লোকেশন নয়।",
        "call_check": "অনুগ্রহ করে ফোন করুন বা দেখুন ট্র্যাকার চার্জ ও চালু আছে কিনা।",
        "no_report": "{l}-এর ট্র্যাকার থেকে এখনও কোনো রিপোর্ট আসেনি।",
        "emergency": "🚨 যদি মনে হয় {l} বিপদে আছে, এখনই 112-এ কল করুন। অ্যাপে: {l}-এর SOS / ম্যাপ স্ক্রিন খুলুন → পথ দেখুন, "
                     "লাইভ লিংক শেয়ার করুন, বা জরুরি – স্কুল / জরুরি – গ্রুপ চাপুন যাতে আশেপাশের লোকেরা সাহায্য করতে পারে।",
        "crisis": "আপনি এই কষ্টের মধ্যে আছেন জেনে দুঃখিত। কেউ তাৎক্ষণিক বিপদে থাকলে এখনই 112-এ কল করুন। সহায়তার জন্য "
                  "Tele-MANAS 14416 (বিনামূল্যে, 24×7) বা Childline 1098-এ কল করুন। আপনি একা নন।",
        "out_of_scope": "দুঃখিত, আমি শুধু {l}-এর ট্র্যাকার নিয়ে বলতে পারি (লোকেশন, পৌঁছানো, যাত্রা, অ্যালার্ট, ব্যাটারি)। "
                        "যেমন: “{l} এখন কোথায়?”, “{l} কখন স্কুলে পৌঁছেছে?”",
    },
}

try:                                           # the other 10 languages
    from .lang_answers_tr import ANS_TR
    ANS.update(ANS_TR)
except ImportError:
    pass
