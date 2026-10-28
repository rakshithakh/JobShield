from app.services.rules import capped_rule_points, detect_rule_signals


def titles(text):
    return {s.title for s in detect_rule_signals(text)}


def test_detects_each_category_with_evidence():
    cases = {
        "Registration/Training Fee": "You must pay a registration fee of Rs 999 to join.",
        "Urgency Tactics": "Only 3 seats left, apply now!",
        "Unrealistic Promises": "No experience needed, guaranteed income.",
        "Suspicious Work Pattern": "Daily payment via UPI after each task.",
        "MLM/Network Marketing": "Build your downline in our network marketing plan.",
        "Too Good To Be True": "Free laptop and a foreign trip for top performers.",
    }
    for cat, text in cases.items():
        sigs = [s for s in detect_rule_signals(text) if s.title == cat]
        assert sigs, cat
        assert sigs[0].evidence and sigs[0].evidence.lower() in text.lower().replace("  ", " ") or sigs[0].evidence


def test_one_signal_per_category_no_double_count():
    text = "Urgent! Apply now, only 3 seats left, hurry, limited slots."
    sigs = [s for s in detect_rule_signals(text) if s.title == "Urgency Tactics"]
    assert len(sigs) == 1 and sigs[0].points == 20


def test_negated_fee_statement_is_not_flagged():
    for t in ["We never ask for any registration fee.", "There is no registration fee or security deposit.",
              "Candidates do not pay a training fee at any stage."]:
        assert "Registration/Training Fee" not in titles(t), t


def test_negation_does_not_leak_across_sentences():
    assert "Registration/Training Fee" in titles("No experience needed. Pay Rs 999 registration fee before joining.")


def test_rule_points_are_capped_at_70():
    text = ("registration fee. urgent. no experience needed. daily payment. network marketing. free laptop.")
    sigs = detect_rule_signals(text)
    assert sum(s.points for s in sigs) > 70
    assert capped_rule_points(sigs) == 70


def test_reworded_advance_fee_scam_is_caught():
    sigs = titles("Earn 3000 daily. Send 500 for starter kit via UPI to confirm your slot. Message us on Telegram.")
    assert "Registration/Training Fee" in sigs and "Suspicious Work Pattern" in sigs


def test_fee_and_no_interview_selection_claim_adds_one_corroborating_signal():
    text = ("Congratulations! You are selected for a Software Engineer job. Salary ₹18 LPA. "
            "No interview required. Pay a refundable registration fee of ₹2,999 today to confirm your offer. "
            "Contact us on WhatsApp immediately.")
    sigs = detect_rule_signals(text)
    bonus = next(s for s in sigs if s.code == "rule:fee_no_interview_offer")
    assert bonus.points == 20
    assert "No interview required" in bonus.evidence and "selected" in bonus.evidence.lower()
    assert capped_rule_points(sigs) == 70


def test_fee_no_interview_and_guarantee_your_job_claim_gets_corroborated():
    text = "Pay Rs 2,999 registration fee to guarantee your job. No interview required. Send payment immediately."
    sigs = detect_rule_signals(text)
    bonus = next(s for s in sigs if s.code == "rule:fee_no_interview_offer")
    assert bonus.points == 20
    assert "guarantee your job" in bonus.evidence.lower()


def test_fee_no_interview_and_immediate_selection_gets_corroborated():
    text = ("Immediate selection without technical interview. Pay Rs 1,500 for mandatory training materials "
            "before receiving your offer letter.")
    sigs = detect_rule_signals(text)
    bonus = next(s for s in sigs if s.code == "rule:fee_no_interview_offer")
    assert bonus.points == 20
    assert "immediate selection" in bonus.evidence.lower()


def test_fee_no_interview_bonus_requires_all_three_cues():
    cases = [
        "No interview required. Congratulations, you are selected for the role.",
        "Congratulations, you are selected for the role. Pay a registration fee. Interview required.",
        "Congratulations, you are selected for the role. No interview required. We never charge a registration fee.",
    ]
    for text in cases:
        assert "rule:fee_no_interview_offer" not in {s.code for s in detect_rule_signals(text)}


def test_requested_otp_over_chat_with_offer_cancellation_deadline_is_high_risk():
    text = ("Your job offer is approved. To release your joining bonus, send your Aadhaar number, "
            "PAN card, bank account number and OTP through WhatsApp. "
            "Complete verification within 30 minutes or your offer will be cancelled.")
    sigs = detect_rule_signals(text)
    sensitive = next(s for s in sigs if s.code == "rule:sensitive_data_request")
    urgency = next(s for s in sigs if s.code == "rule:urgency_tactics")
    assert sensitive.points == 60
    assert "OTP" in sensitive.evidence and "WhatsApp" in sensitive.evidence
    assert urgency.points == 20
    assert capped_rule_points(sigs) == 70


def test_chat_otp_warning_and_non_otp_post_offer_request_do_not_get_critical_signal():
    safety_advice = "Never share your OTP through WhatsApp. Verify the employer independently."
    post_offer = "After the signed offer, send bank account details through WhatsApp to HR."
    for text in (safety_advice, post_offer):
        assert "rule:sensitive_data_request" not in {s.code for s in detect_rule_signals(text)}


def test_offer_cancellation_deadline_adds_urgency_only_with_consequence():
    assert "Urgency Tactics" in titles("Verify within 30 minutes or your offer will be cancelled.")
    assert "Urgency Tactics" not in titles("Please complete verification within 30 minutes to continue onboarding.")


def test_upfront_upi_fee_with_confirmed_placement_and_no_interview_gets_corroborated():
    text = ("Dear candidate, your placement is confirmed at a top IT company. "
            "Pay a refundable security deposit of ₹5,000 by UPI to reserve your seat. "
            "The company guarantees employment after payment. No interview or technical round will be conducted.")
    sigs = detect_rule_signals(text)
    assert "Registration/Training Fee" in {s.title for s in sigs}
    assert "Suspicious Work Pattern" in {s.title for s in sigs}
    assert "rule:fee_no_interview_offer" in {s.code for s in sigs}
    assert capped_rule_points(sigs) == 70


def test_guaranteed_placement_alone_does_not_add_fee_offer_bonus():
    text = "Placement is confirmed. No interview will be conducted for this short contract role."
    assert "rule:fee_no_interview_offer" not in {s.code for s in detect_rule_signals(text)}


def test_priced_training_with_guaranteed_placement_and_no_checks_is_flagged_once_per_signal():
    text = (
        "Join our three-day software engineering training program for ₹12,999. "
        "Every participant is guaranteed a ₹12 LPA job at a multinational company immediately after completing the course. "
        "No assessment or interview required. Pay the full amount today to receive your placement confirmation letter. "
        "Fees are non-refundable, regardless of placement outcome."
    )
    sigs = detect_rule_signals(text)
    codes = {signal.code for signal in sigs}
    assert "rule:registration_training_fee" in codes
    assert "rule:unrealistic_promises" in codes
    assert "rule:fee_no_interview_offer" in codes
    assert sum(signal.code == "rule:registration_training_fee" for signal in sigs) == 1
    assert capped_rule_points(sigs) == 70
    fee = next(signal for signal in sigs if signal.code == "rule:registration_training_fee")
    assert "training program" in fee.evidence.lower() and "12,999" in fee.evidence


def test_paid_training_without_a_job_placement_guarantee_is_not_flagged_as_a_hiring_fee():
    text = "Join our three-day software engineering training program for ₹12,999. Includes practical workshops."
    assert "Registration/Training Fee" not in titles(text)
    assert "Unrealistic Promises" not in titles(text)


def test_sensitive_documents_requested_by_messaging_during_no_interview_hiring():
    text = ("Remote Software Developer. No technical interview required. "
            "Guaranteed job offer within 24 hours. Candidates must send their Aadhaar card, "
            "PAN card and bank account details over WhatsApp to complete immediate onboarding.")
    sig = next(s for s in detect_rule_signals(text) if s.code == "rule:sensitive_data_request")
    assert sig.points == 35
    assert sig.evidence and "Aadhaar card" in sig.evidence and "WhatsApp" in sig.evidence
    assert sig.evidence[slice(*sig.evidence_span)] == "must send their Aadhaar card"


def test_sensitive_document_rule_ignores_post_offer_secure_portal_and_safety_advice():
    legitimate = ("After the interview and signed offer, submit PAN and bank account details "
                  "through the employer's secure HR portal.")
    safety_advice = ("Never send your Aadhaar card, PAN card or bank details over WhatsApp. "
                     "A legitimate employer will verify you after an interview and formal offer.")
    for text in (legitimate, safety_advice):
        assert "rule:sensitive_data_request" not in {s.code for s in detect_rule_signals(text)}


def test_sensitive_data_request_is_one_signal_and_card_photo_gets_strong_weight():
    text = ("Before scheduling an interview, send your Aadhaar number, PAN card, bank account details, "
            "and a photo of your debit card to our recruitment team.")
    sigs = detect_rule_signals(text)
    sensitive = [s for s in sigs if s.code == "rule:sensitive_data_request"]
    assert len(sensitive) == 1 and sensitive[0].points == 60
    assert "debit card" in sensitive[0].evidence.lower()
    assert sensitive[0].evidence[slice(*sensitive[0].evidence_span)].lower().startswith("send")


def test_authentication_secret_requests_are_strongly_flagged():
    for secret in ("OTP", "PIN", "CVV"):
        sig = next(s for s in detect_rule_signals(f"Send your {secret} to the recruiter to verify your application.")
                   if s.code == "rule:sensitive_data_request")
        assert sig.points == 60 and sig.severity == "high"


def test_bank_details_before_interview_are_flagged_but_post_hire_payroll_is_not():
    early = detect_rule_signals("Before your interview, send your bank account details to recruitment.")
    assert next(s for s in early if s.code == "rule:sensitive_data_request").points == 35
    payroll = "Bank details are collected after hiring for payroll and salary deposits."
    assert "rule:sensitive_data_request" not in {s.code for s in detect_rule_signals(payroll)}


def test_safety_warning_and_clean_software_job_are_not_flagged():
    warning = "Never share your PIN or OTP with anyone during recruitment."
    clean = "We are hiring a software engineer with Python experience to build web services."
    for text in (warning, clean):
        assert "rule:sensitive_data_request" not in {s.code for s in detect_rule_signals(text)}


def test_clean_text_has_no_signals():
    assert detect_rule_signals("We are hiring a backend engineer with 3 years of Python experience in Pune.") == []


def test_evidence_span_marks_exactly_the_matched_phrase():
    text = "Great team.   Only 3 seats left,  pay Rs 999 registration fee before joining the company. Daily payment via UPI after tasks."
    for s in detect_rule_signals(text):
        a, b = s.evidence_span
        assert 0 <= a < b <= len(s.evidence)
        assert s.evidence[a:b].lower() in text.lower().replace("  ", " ")
    fee = next(s for s in detect_rule_signals(text) if s.title == "Registration/Training Fee")
    assert fee.evidence[slice(*fee.evidence_span)].lower() == "registration fee"


def test_excerpts_do_not_cut_words_and_use_ellipses():
    text = "x" * 5 + " " + "lorem ipsum dolor sit amet consectetur " * 3 + "pay Rs 999 registration fee now " + "adipiscing elit sed do eiusmod " * 3
    sig = next(s for s in detect_rule_signals(text) if s.title == "Registration/Training Fee")
    assert sig.evidence.startswith("\u2026") and sig.evidence.endswith("\u2026")
    inner = sig.evidence.strip("\u2026")
    assert all(w in text.split() for w in inner.split())          # only whole words
    assert len(sig.evidence) < 200
