let assessments = {};
let currentJD = null;
let currentJDKey = "";
let candidateName = "";
let currentQuestionIndex = 0;
let answers = [];
let timer = null;
let timeLeft = 15 * 60; // 15 minutes in seconds

// Selectors
const selectorScreen = document.getElementById('selector-screen');
const assessmentScreen = document.getElementById('assessment-screen');
const loadingScreen = document.getElementById('loading-screen');
const resultScreen = document.getElementById('result-screen');
const jdSelect = document.getElementById('jd-select');
const jdUpload = document.getElementById('jd-upload');
const jdProgressContainer = document.getElementById('jd-progress-container');
const jdProgressBar = document.getElementById('jd-progress-bar');
const jdProgressStatus = document.getElementById('jd-progress-status');
const fileNameDisplay = document.getElementById('file-name-display');
const nameInput = document.getElementById('candidate-name');
const startBtn = document.getElementById('start-btn');
const roleTitle = document.getElementById('role-title');
const questionContainer = document.getElementById('question-container');
const scenarioText = document.getElementById('scenario-text');
const questionText = document.getElementById('question-text');
const answerInput = document.getElementById('answer-input');
const nextBtn = document.getElementById('next-btn');
const progressFill = document.getElementById('progress-fill');
const timerDisplay = document.getElementById('time-left');

// Initialize
async function init() {
    try {
        const response = await fetch('assessments.json');
        assessments = await response.json();
        populateDropdown();
    } catch (error) {
        console.error('Error loading assessments:', error);
        alert('Failed to load assessments. Please ensure assessments.json exists.');
    }
}

function populateDropdown() {
    Object.keys(assessments).forEach(key => {
        const data = assessments[key];
        if (data.error) return; // Skip errors

        const option = document.createElement('option');
        option.value = key;
        // Clean display name (e.g., Company\Role.pdf -> Role (Company))
        const parts = key.split('\\');
        const company = data.company || parts[0];
        const role = data.role || parts[parts.length - 1].replace('.pdf.pdf', '');
        option.textContent = `${role} at ${company}`;
        jdSelect.appendChild(option);
    });
}

startBtn.addEventListener('click', () => {
    const selectedKey = jdSelect.value;
    candidateName = nameInput.value.trim();

    if (!candidateName) return alert('Please enter your name.');
    if (!selectedKey) return alert('Please select a JD.');

    currentJDKey = selectedKey;
    currentJD = assessments[selectedKey];
    startAssessment();
});

jdUpload.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    fileNameDisplay.textContent = file.name;
    jdProgressContainer.classList.remove('hidden');
    jdProgressStatus.style.color = 'var(--text-secondary)';

    const formData = new FormData();
    formData.append('file', file);

    try {
        updateJDProgress(10, 'Extracting text from PDF...');

        const response = await fetch('/upload-jd', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('Upload failed');

        updateJDProgress(40, 'Structuring Job Description...');
        await new Promise(r => setTimeout(r, 800));

        updateJDProgress(70, 'Generating assessment questions...');
        await new Promise(r => setTimeout(r, 1200));

        const result = await response.json();

        updateJDProgress(100, 'Ready! Starting assessment...');
        await new Promise(r => setTimeout(r, 800));

        // Refresh assessments list
        const res = await fetch('assessments.json');
        assessments = await res.json();

        // Re-populate dropdown to include new JD
        jdSelect.innerHTML = '<option value="" disabled selected>Choose a Job Description...</option>';
        populateDropdown();

        // Auto-select and start
        jdSelect.value = result.jd_key;
        currentJDKey = result.jd_key;
        currentJD = assessments[result.jd_key];

        candidateName = nameInput.value.trim();
        if (!candidateName) {
            jdProgressContainer.classList.add('hidden');
            alert('JD Processed! Please enter your name and click Start.');
            return;
        }

        startAssessment();

    } catch (error) {
        console.error('JD Processing error:', error);
        jdProgressStatus.textContent = 'Error processing JD. Please try again.';
        jdProgressStatus.style.color = 'var(--error)';
    }
});

function updateJDProgress(percent, status) {
    jdProgressBar.style.width = percent + '%';
    jdProgressStatus.textContent = status;
}

function startAssessment() {
    selectorScreen.classList.add('hidden');
    assessmentScreen.classList.remove('hidden');
    assessmentScreen.classList.add('fade-in');

    currentQuestionIndex = 0;
    answers = [];
    roleTitle.textContent = `${currentJD.role} - ${currentJD.company}`;

    updateQuestion();
    startTimer();
}

function updateQuestion() {
    const questions = currentJD.assessment_questions;
    const q = questions[currentQuestionIndex];

    scenarioText.textContent = q.scenario;
    questionText.textContent = q.question;
    answerInput.value = '';

    // Update Progress
    const progress = ((currentQuestionIndex + 1) / questions.length) * 100;
    progressFill.style.width = `${progress}%`;

    // Update Button Text
    if (currentQuestionIndex === questions.length - 1) {
        nextBtn.textContent = 'Submit Assessment';
    } else {
        nextBtn.textContent = 'Next Question';
    }
}

nextBtn.addEventListener('click', () => {
    const response = answerInput.value.trim();
    if (!response) return alert('Please provide an answer before continuing.');

    answers.push({
        question: currentJD.assessment_questions[currentQuestionIndex].question,
        scenario: currentJD.assessment_questions[currentQuestionIndex].scenario,
        response: response
    });

    if (currentQuestionIndex < currentJD.assessment_questions.length - 1) {
        currentQuestionIndex++;
        updateQuestion();
    } else {
        submitAssessment();
    }
});

function startTimer() {
    timer = setInterval(() => {
        timeLeft--;
        if (timeLeft <= 0) {
            clearInterval(timer);
            alert('Time is up! Submitting your current progress.');
            submitAssessment();
        }
        updateTimerDisplay();
    }, 1000);
}

function updateTimerDisplay() {
    const mins = Math.floor(timeLeft / 60);
    const secs = timeLeft % 60;
    timerDisplay.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
}

async function submitAssessment() {
    clearInterval(timer);

    const submission = {
        candidate_name: candidateName,
        jd_file: currentJDKey,
        role: currentJD.role,
        company: currentJD.company,
        timestamp: new Date().toISOString(),
        responses: answers
    };

    try {
        assessmentScreen.classList.add('hidden');
        loadingScreen.classList.remove('hidden');
        loadingScreen.classList.add('fade-in');

        const res = await fetch('/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(submission)
        });

        if (res.ok) {
            const result = await res.json();
            const evaluation = result.evaluation;

            loadingScreen.classList.add('hidden');
            resultScreen.classList.remove('hidden');
            resultScreen.classList.add('fade-in');

            // Show score
            document.getElementById('final-score-val').textContent = evaluation.total_score;
            document.getElementById('rec-text').textContent = evaluation.recommendation;
            document.getElementById('rec-text').className = `rec-${evaluation.recommendation.toLowerCase()}`;
            document.getElementById('feedback-preview').textContent = evaluation.detailed_feedback;

        } else {
            throw new Error('Failed to submit');
        }
    } catch (error) {
        console.error('Submission error:', error);
        loadingScreen.classList.add('hidden');
        assessmentScreen.classList.remove('hidden');
        alert('There was an error saving your results. Please try again.');
    }
}

init();
