package com.selfxtrack.app.i18n

/** Translations for: Devices (home), Auth, Verify phone, Plans, common helpers. */
internal val trMain = Tr(
    hi = mapOf(
        // Common
        "never" to "कभी नहीं",
        "just now" to "अभी-अभी",
        "{0} min ago" to "{0} मिनट पहले",
        "{0} h ago" to "{0} घंटे पहले",
        "{0} d ago" to "{0} दिन पहले",
        "Live location of {0} (valid {1}): {2}" to "{0} की लाइव लोकेशन ({1} तक मान्य): {2}",
        "my child" to "मेरे बच्चे",
        "{0} h" to "{0} घंटे",
        "{0} min" to "{0} मिनट",
        "Share live location" to "लाइव लोकेशन शेयर करें",
        "Cancel" to "रद्द करें",

        // Auth
        "Family safety tracker" to "परिवार सुरक्षा ट्रैकर",
        "Your name" to "आपका नाम",
        "Email" to "ईमेल",
        "Password" to "पासवर्ड",
        "Server address" to "सर्वर पता",
        "I agree to the Terms and Privacy Policy and give consent, as parent / guardian, for my child's location to be processed for safety." to
            "मैं नियम और प्राइवेसी पॉलिसी से सहमत हूँ, और माता-पिता / अभिभावक के रूप में सुरक्षा के लिए अपने बच्चे की लोकेशन इस्तेमाल करने की अनुमति देता/देती हूँ।",
        "Privacy Policy" to "प्राइवेसी पॉलिसी",
        "Terms" to "नियम",
        "Create account" to "अकाउंट बनाएँ",
        "Log in" to "लॉग इन करें",
        "Have an account? Log in" to "पहले से अकाउंट है? लॉग इन करें",
        "New here? Create an account" to "नए हैं? अकाउंट बनाएँ",
        "Forgot password?" to "पासवर्ड भूल गए?",
        "Reset password" to "पासवर्ड रीसेट करें",
        "Account email" to "अकाउंट का ईमेल",
        "OTP sent to your mobile" to "आपके मोबाइल पर भेजा गया OTP",
        "New password (8+)" to "नया पासवर्ड (8+ अक्षर)",
        "Test mode OTP: {0}" to "टेस्ट मोड OTP: {0}",
        "Password changed. Log in with the new password." to "पासवर्ड बदल गया। नए पासवर्ड से लॉग इन करें।",
        "Change password" to "पासवर्ड बदलें",
        "Send OTP" to "OTP भेजें",

        // Verify phone
        "Verify your mobile" to "अपना मोबाइल वेरिफ़ाई करें",
        "For everyone's safety, every SelfXTrack account verifies a mobile number. It is used for emergency alerts and password recovery." to
            "सबकी सुरक्षा के लिए हर SelfXTrack अकाउंट का मोबाइल नंबर वेरिफ़ाई होता है। इसका इस्तेमाल इमरजेंसी अलर्ट और पासवर्ड वापस पाने के लिए होता है।",
        "Mobile number" to "मोबाइल नंबर",
        "6-digit OTP" to "6 अंकों का OTP",
        "Verify" to "वेरिफ़ाई करें",
        "Change number / resend" to "नंबर बदलें / दोबारा भेजें",

        // Plans
        "Plans" to "प्लान",
        "Back" to "वापस",
        "Your plan: {0}" to "आपका प्लान: {0}",
        "valid till {0}" to "{0} तक मान्य",
        "payment failed – {0}-day grace" to "पेमेंट नहीं हुआ – {0} दिन की छूट",
        "will not renew" to "रिन्यू नहीं होगा",
        "SOS to family, Call 112 and live location always work – even if a payment fails." to
            "परिवार को SOS, 112 पर कॉल और लाइव लोकेशन हमेशा काम करते हैं – पेमेंट न होने पर भी।",
        "Monthly" to "मासिक",
        "Yearly (save ~16%)" to "सालाना (~16% बचत)",
        "year" to "साल",
        "month" to "महीना",
        "✅ Current plan" to "✅ मौजूदा प्लान",
        "Complete the payment (UPI AutoPay / card) in the browser, then come back." to
            "ब्राउज़र में पेमेंट (UPI AutoPay / कार्ड) पूरा करें, फिर वापस आएँ।",
        "Choose {0}" to "{0} चुनें",
        "Auto-renew stopped." to "ऑटो-रिन्यू बंद हो गया।",
        "Stop auto-renew" to "ऑटो-रिन्यू बंद करें",
        "Test payment" to "टेस्ट पेमेंट",
        "Payments are in test mode (no Razorpay keys on the server). Confirm ₹{0} for {1}?" to
            "पेमेंट अभी टेस्ट मोड में है (सर्वर पर Razorpay keys नहीं हैं)। {1} के लिए ₹{0} कन्फ़र्म करें?",
        "{0} plan active." to "{0} प्लान चालू है।",
        "Pay (test)" to "पेमेंट करें (टेस्ट)",

        // Devices
        "Help children nearby" to "आस-पास के बच्चों की मदद करें",
        "When a family nearby presses “Emergency – Group”, you get an alert. Your approximate location is used only to find you; families see your name and position only if you tap “I can help”." to
            "जब आस-पास कोई परिवार “इमरजेंसी – ग्रुप” दबाता है, तो आपको अलर्ट मिलता है। आपकी अनुमानित लोकेशन सिर्फ़ आपको ढूँढने के लिए इस्तेमाल होती है; परिवार आपका नाम और जगह तभी देखते हैं जब आप “मैं मदद कर सकता/सकती हूँ” दबाते हैं।",
        "Available to help" to "मदद के लिए उपलब्ध",
        "Done" to "हो गया",
        "Log out?" to "लॉग आउट करें?",
        "Do you want to log out? You will NOT receive SOS or safety alerts on this phone until you log in again." to
            "क्या आप लॉग आउट करना चाहते हैं? दोबारा लॉग इन करने तक इस फ़ोन पर SOS या सुरक्षा अलर्ट नहीं मिलेंगे।",
        "Log out" to "लॉग आउट",
        "My family" to "मेरा परिवार",
        "School dashboard" to "स्कूल डैशबोर्ड",
        "Help nearby" to "आस-पास मदद",
        "Account & privacy" to "अकाउंट और प्राइवेसी",
        "Add tracker" to "ट्रैकर जोड़ें",
        "No trackers yet. Tap \"Add tracker\" and enter the code from the box." to
            "अभी कोई ट्रैकर नहीं है। \"ट्रैकर जोड़ें\" दबाएँ और डिब्बे पर लिखा कोड डालें।",
        "🚨 SOS ACTIVE – tap now" to "🚨 SOS चालू – अभी दबाएँ",
        "Online · {0}" to "ऑनलाइन · {0}",
        "Offline · last seen {0}" to "ऑफ़लाइन · आख़िरी बार {0}",
        "Child setup" to "बच्चे की सेटिंग",
        "📄 Privacy Policy" to "📄 प्राइवेसी पॉलिसी",
        "📄 Terms of Use" to "📄 इस्तेमाल के नियम",
        "Save / share my data" to "मेरा डेटा सेव / शेयर करें",
        "⬇️ Download my data" to "⬇️ मेरा डेटा डाउनलोड करें",
        "🗑 Delete my account" to "🗑 मेरा अकाउंट डिलीट करें",
        "This permanently deletes your account. Trackers you own are released and their history is erased. Enter your password to confirm." to
            "इससे आपका अकाउंट हमेशा के लिए डिलीट हो जाएगा। आपके ट्रैकर हटा दिए जाएँगे और उनकी हिस्ट्री मिट जाएगी। पक्का करने के लिए अपना पासवर्ड डालें।",
        "Delete permanently" to "हमेशा के लिए डिलीट करें",
        "Close" to "बंद करें",
    ),
    bn = mapOf(
        // Common
        "never" to "কখনও না",
        "just now" to "এইমাত্র",
        "{0} min ago" to "{0} মিনিট আগে",
        "{0} h ago" to "{0} ঘণ্টা আগে",
        "{0} d ago" to "{0} দিন আগে",
        "Live location of {0} (valid {1}): {2}" to "{0}-এর লাইভ লোকেশন ({1} পর্যন্ত বৈধ): {2}",
        "my child" to "আমার সন্তান",
        "{0} h" to "{0} ঘণ্টা",
        "{0} min" to "{0} মিনিট",
        "Share live location" to "লাইভ লোকেশন শেয়ার করুন",
        "Cancel" to "বাতিল",

        // Auth
        "Family safety tracker" to "পরিবারের সুরক্ষা ট্র্যাকার",
        "Your name" to "আপনার নাম",
        "Email" to "ইমেল",
        "Password" to "পাসওয়ার্ড",
        "Server address" to "সার্ভারের ঠিকানা",
        "I agree to the Terms and Privacy Policy and give consent, as parent / guardian, for my child's location to be processed for safety." to
            "আমি শর্তাবলী ও প্রাইভেসি পলিসিতে সম্মত, এবং বাবা-মা / অভিভাবক হিসেবে সুরক্ষার জন্য আমার সন্তানের লোকেশন ব্যবহারের অনুমতি দিচ্ছি।",
        "Privacy Policy" to "প্রাইভেসি পলিসি",
        "Terms" to "শর্তাবলী",
        "Create account" to "অ্যাকাউন্ট খুলুন",
        "Log in" to "লগ ইন করুন",
        "Have an account? Log in" to "অ্যাকাউন্ট আছে? লগ ইন করুন",
        "New here? Create an account" to "নতুন? অ্যাকাউন্ট খুলুন",
        "Forgot password?" to "পাসওয়ার্ড ভুলে গেছেন?",
        "Reset password" to "পাসওয়ার্ড রিসেট করুন",
        "Account email" to "অ্যাকাউন্টের ইমেল",
        "OTP sent to your mobile" to "আপনার মোবাইলে পাঠানো OTP",
        "New password (8+)" to "নতুন পাসওয়ার্ড (8+ অক্ষর)",
        "Test mode OTP: {0}" to "টেস্ট মোড OTP: {0}",
        "Password changed. Log in with the new password." to "পাসওয়ার্ড বদলানো হয়েছে। নতুন পাসওয়ার্ড দিয়ে লগ ইন করুন।",
        "Change password" to "পাসওয়ার্ড বদলান",
        "Send OTP" to "OTP পাঠান",

        // Verify phone
        "Verify your mobile" to "আপনার মোবাইল যাচাই করুন",
        "For everyone's safety, every SelfXTrack account verifies a mobile number. It is used for emergency alerts and password recovery." to
            "সবার সুরক্ষার জন্য প্রতিটি SelfXTrack অ্যাকাউন্টে একটি মোবাইল নম্বর যাচাই করা হয়। এটি জরুরি অ্যালার্ট ও পাসওয়ার্ড ফিরে পেতে ব্যবহার হয়।",
        "Mobile number" to "মোবাইল নম্বর",
        "6-digit OTP" to "6 সংখ্যার OTP",
        "Verify" to "যাচাই করুন",
        "Change number / resend" to "নম্বর বদলান / আবার পাঠান",

        // Plans
        "Plans" to "প্ল্যান",
        "Back" to "ফিরে যান",
        "Your plan: {0}" to "আপনার প্ল্যান: {0}",
        "valid till {0}" to "{0} পর্যন্ত বৈধ",
        "payment failed – {0}-day grace" to "পেমেন্ট হয়নি – {0} দিনের ছাড়",
        "will not renew" to "রিনিউ হবে না",
        "SOS to family, Call 112 and live location always work – even if a payment fails." to
            "পরিবারকে SOS, 112-এ কল আর লাইভ লোকেশন সবসময় কাজ করে – পেমেন্ট না হলেও।",
        "Monthly" to "মাসিক",
        "Yearly (save ~16%)" to "বার্ষিক (~16% সাশ্রয়)",
        "year" to "বছর",
        "month" to "মাস",
        "✅ Current plan" to "✅ বর্তমান প্ল্যান",
        "Complete the payment (UPI AutoPay / card) in the browser, then come back." to
            "ব্রাউজারে পেমেন্ট (UPI AutoPay / কার্ড) সম্পূর্ণ করুন, তারপর ফিরে আসুন।",
        "Choose {0}" to "{0} বেছে নিন",
        "Auto-renew stopped." to "অটো-রিনিউ বন্ধ হয়েছে।",
        "Stop auto-renew" to "অটো-রিনিউ বন্ধ করুন",
        "Test payment" to "টেস্ট পেমেন্ট",
        "Payments are in test mode (no Razorpay keys on the server). Confirm ₹{0} for {1}?" to
            "পেমেন্ট এখন টেস্ট মোডে আছে (সার্ভারে Razorpay keys নেই)। {1}-এর জন্য ₹{0} নিশ্চিত করবেন?",
        "{0} plan active." to "{0} প্ল্যান চালু হয়েছে।",
        "Pay (test)" to "পেমেন্ট করুন (টেস্ট)",

        // Devices
        "Help children nearby" to "কাছাকাছি শিশুদের সাহায্য করুন",
        "When a family nearby presses “Emergency – Group”, you get an alert. Your approximate location is used only to find you; families see your name and position only if you tap “I can help”." to
            "কাছাকাছি কোনো পরিবার “জরুরি – গ্রুপ” চাপলে আপনি অ্যালার্ট পাবেন। আপনার আনুমানিক লোকেশন শুধু আপনাকে খুঁজে পেতে ব্যবহার হয়; আপনি “আমি সাহায্য করতে পারি” চাপলে তবেই পরিবার আপনার নাম ও অবস্থান দেখতে পায়।",
        "Available to help" to "সাহায্যের জন্য প্রস্তুত",
        "Done" to "হয়ে গেছে",
        "Log out?" to "লগ আউট করবেন?",
        "Do you want to log out? You will NOT receive SOS or safety alerts on this phone until you log in again." to
            "আপনি কি লগ আউট করতে চান? আবার লগ ইন না করা পর্যন্ত এই ফোনে SOS বা সুরক্ষা অ্যালার্ট পাবেন না।",
        "Log out" to "লগ আউট",
        "My family" to "আমার পরিবার",
        "School dashboard" to "স্কুল ড্যাশবোর্ড",
        "Help nearby" to "কাছাকাছি সাহায্য",
        "Account & privacy" to "অ্যাকাউন্ট ও প্রাইভেসি",
        "Add tracker" to "ট্র্যাকার যোগ করুন",
        "No trackers yet. Tap \"Add tracker\" and enter the code from the box." to
            "এখনও কোনো ট্র্যাকার নেই। \"ট্র্যাকার যোগ করুন\" চাপুন আর বাক্সে লেখা কোড দিন।",
        "🚨 SOS ACTIVE – tap now" to "🚨 SOS চালু – এখনই চাপুন",
        "Online · {0}" to "অনলাইন · {0}",
        "Offline · last seen {0}" to "অফলাইন · শেষ দেখা {0}",
        "Child setup" to "সন্তানের সেটিং",
        "📄 Privacy Policy" to "📄 প্রাইভেসি পলিসি",
        "📄 Terms of Use" to "📄 ব্যবহারের শর্তাবলী",
        "Save / share my data" to "আমার ডেটা সেভ / শেয়ার করুন",
        "⬇️ Download my data" to "⬇️ আমার ডেটা ডাউনলোড করুন",
        "🗑 Delete my account" to "🗑 আমার অ্যাকাউন্ট ডিলিট করুন",
        "This permanently deletes your account. Trackers you own are released and their history is erased. Enter your password to confirm." to
            "এতে আপনার অ্যাকাউন্ট চিরতরে ডিলিট হয়ে যাবে। আপনার ট্র্যাকারগুলো সরিয়ে দেওয়া হবে এবং তাদের হিস্ট্রি মুছে যাবে। নিশ্চিত করতে আপনার পাসওয়ার্ড দিন।",
        "Delete permanently" to "চিরতরে ডিলিট করুন",
        "Close" to "বন্ধ করুন",
    ),
)
