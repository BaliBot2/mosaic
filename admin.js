let assessments = {};

const tabJds = document.getElementById('tab-jds');
const tabLeaderboard = document.getElementById('tab-leaderboard');
const viewJds = document.getElementById('view-jds');
const viewLeaderboard = document.getElementById('view-leaderboard');
const jdSelect = document.getElementById('admin-jd-select');
const pdfContainer = document.getElementById('pdf-container');
const pdfFrame = document.getElementById('pdf-frame');
const noJdSelected = document.getElementById('no-jd-selected');
const assessRole = document.getElementById('assess-role');
const questionsList = document.getElementById('questions-list');
const assessmentDetails = document.getElementById('assessment-details');

async function init() {
    try {
        const response = await fetch('/assessments.json');
        assessments = await response.json();
        populateJdDropdown();
        fetchLeaderboard();
    } catch (error) {
        console.error('Error loading data:', error);
    }
}

function switchTab(tab) {
    if (tab === 'jds') {
        tabJds.classList.add('active');
        tabLeaderboard.classList.remove('active');
        viewJds.classList.remove('hidden');
        viewLeaderboard.classList.add('hidden');
        
        // Re-apply inline style for dual-pane grid that hidden removes
        viewJds.style.display = 'grid'; 
    } else {
        tabLeaderboard.classList.add('active');
        tabJds.classList.remove('active');
        viewLeaderboard.classList.remove('hidden');
        viewJds.classList.add('hidden');
        viewJds.style.display = 'none';
    }
}

function populateJdDropdown() {
    jdSelect.innerHTML = '<option value="" disabled selected>Select a Job Description...</option>';
    Object.keys(assessments).forEach(key => {
        const data = assessments[key];
        if (data.error) return;

        const option = document.createElement('option');
        option.value = key;
        const company = data.company || key.split('\\')[0];
        const role = data.role || 'Role';
        option.textContent = `${role} at ${company}`;
        jdSelect.appendChild(option);
    });
}

jdSelect.addEventListener('change', (e) => {
    const key = e.target.value;
    const data = assessments[key];
    
    // Show PDF
    // Check if it's an uploaded PDF (has .pdf extension usually, stored in uploads folder)
    // Or a sample PDF (stored in data/pdfs)
    const isUpload = key.includes('uploads/') || key.endsWith('.pdf');
    // Assuming backend serves /uploads/filename.pdf
    const pdfUrl = key.includes('\\') ? `/data/pdfs/${key.replace(/\\/g, '/')}` : `/uploads/${key}`;
    
    noJdSelected.classList.add('hidden');
    pdfContainer.classList.remove('hidden');
    pdfFrame.src = pdfUrl;

    // Show Assessment
    assessmentDetails.classList.remove('hidden');
    assessRole.textContent = `${data.role} Assessment Criteria`;
    
    questionsList.innerHTML = '';
    data.assessment_questions.forEach((q, i) => {
        const qCard = document.createElement('div');
        qCard.className = 'question-card';
        qCard.innerHTML = `
            <div style="font-weight: 700; margin-bottom: 8px;">Q${i+1}: ${q.question}</div>
            <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 12px; font-style: italic;">Scenario: ${q.scenario}</div>
            <div style="font-size: 0.9rem; border-top: 1px dotted var(--glass-border); padding-top: 8px;">
                <span style="color: var(--accent-purple); font-weight: 600;">What we look for:</span> ${q.evaluation_criteria}
            </div>
        `;
        questionsList.appendChild(qCard);
    });
});

async function fetchLeaderboard() {
    try {
        const response = await fetch('/leaderboard-data');
        const data = await response.json();
        
        const tableBody = document.getElementById('leaderboard-body');
        const noDataMsg = document.getElementById('no-data-msg');
        tableBody.innerHTML = '';
        
        if (data.length === 0) {
            noDataMsg.classList.remove('hidden');
            return;
        }
        
        // Sort by score descending
        data.sort((a, b) => b.total_score - a.total_score);
        
        data.forEach(candidate => {
            const row = document.createElement('tr');
            
            // Format recommendation visually
            let recClass = '';
            if (candidate.recommendation.toLowerCase().includes('advance')) recClass = 'rec-advance';
            else if (candidate.recommendation.toLowerCase().includes('hold')) recClass = 'rec-hold';
            else recClass = 'rec-reject';

            row.innerHTML = `
                <td style="font-weight: 600;">${candidate.candidate_name}</td>
                <td style="color: var(--text-secondary);">${candidate.role}</td>
                <td><span class="score-badge">${candidate.total_score}/100</span></td>
                <td class="${recClass}">${candidate.recommendation}</td>
                <td style="font-size: 0.85rem;">${candidate.strengths.slice(0, 2).join('<br>')}</td>
            `;
            tableBody.appendChild(row);
        });
        
    } catch (error) {
        console.error('Error fetching leaderboard:', error);
    }
}

init();
