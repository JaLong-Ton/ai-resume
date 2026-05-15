/**
 * AI Resume Analyzer - Frontend Application
 * Single-page app: upload PDF, view extracted info and match scores.
 */

// =========================================================================
// Configuration - Update API_BASE_URL after deploying backend to FC
// =========================================================================
const API_BASE_URL = 'https://resume-analyzer-spucnjlkdu.cn-hangzhou.fcapp.run';

// =========================================================================
// DOM References
// =========================================================================
const $uploadArea = document.getElementById('uploadArea');
const $fileInput = document.getElementById('fileInput');
const $fileInfo = document.getElementById('fileInfo');
const $fileName = document.getElementById('fileName');
const $analyzeBtn = document.getElementById('analyzeBtn');
const $jobDesc = document.getElementById('jobDesc');
const $loading = document.getElementById('loadingOverlay');
const $resultsCard = document.getElementById('resultsCard');
const $resultsBody = document.getElementById('resultsBody');
const $timeBadge = document.getElementById('timeBadge');
const $toastContainer = document.getElementById('toastContainer');

let selectedFile = null;

// =========================================================================
// File Selection
// =========================================================================

$uploadArea.addEventListener('click', () => $fileInput.click());

$uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    $uploadArea.classList.add('dragover');
});

$uploadArea.addEventListener('dragleave', () => {
    $uploadArea.classList.remove('dragover');
});

$uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    $uploadArea.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) setFile(files[0]);
});

$fileInput.addEventListener('change', () => {
    if ($fileInput.files.length > 0) setFile($fileInput.files[0]);
});

function setFile(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showToast('仅支持 PDF 格式文件', 'error');
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        showToast('文件大小超过 10MB 限制', 'error');
        return;
    }
    selectedFile = file;
    $uploadArea.classList.add('has-file');
    $fileInfo.classList.add('show');
    $fileName.textContent = file.name;
    $analyzeBtn.disabled = false;
}

// =========================================================================
// Analyze
// =========================================================================

$analyzeBtn.addEventListener('click', () => {
    if (!selectedFile) return;
    performAnalysis();
});

async function performAnalysis() {
    $loading.classList.add('show');
    $resultsCard.classList.add('hidden');
    $analyzeBtn.disabled = true;

    const formData = new FormData();
    formData.append('file', selectedFile);
    const jd = $jobDesc.value.trim();
    if (jd) formData.append('job_description', jd);

    const endpoint = jd ? `${API_BASE_URL}/api/analyze` : `${API_BASE_URL}/api/upload`;

    try {
        const response = await fetch(endpoint, { method: 'POST', body: formData });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || (data.error && data.error.message) || '请求失败');
        }

        if (!data.success) {
            throw new Error((data.error && data.error.message) || '分析失败');
        }

        renderResults(data.data);
        $resultsCard.classList.remove('hidden');
        $resultsCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
        showToast(err.message || '网络错误，请检查后端服务是否启动', 'error');
    } finally {
        $loading.classList.remove('show');
        $analyzeBtn.disabled = false;
    }
}

// =========================================================================
// Render Results
// =========================================================================

function renderResults(data) {
    const { extracted_info, matching, processing_time_ms, file_name } = data;
    const ei = extracted_info;

    // Processing time badge
    const cacheLabel = data.from_cache ? ' · 缓存命中' : '';
    $timeBadge.textContent = `耗时 ${(processing_time_ms / 1000).toFixed(1)}s${cacheLabel}`;
    if (data.from_cache) {
        $timeBadge.className = 'badge badge-success';
    } else {
        $timeBadge.className = 'badge badge-primary';
    }

    // Match score class
    let scoreClass = 'match-low';
    if (matching) {
        const s = matching.match_score;
        if (s >= 0.7) scoreClass = 'match-high';
        else if (s >= 0.4) scoreClass = 'match-medium';
    }

    let html = '';

    // -- Basic Info --
    html += '<div class="section">';
    html += '<div class="section-title">基本信息</div>';
    html += '<div class="info-grid">';
    html += infoItem('姓名', ei.name);
    html += infoItem('电话', ei.phone);
    html += infoItem('邮箱', ei.email);
    html += infoItem('地址', ei.address);
    html += infoItem('求职意向', ei.job_intention);
    html += infoItem('期望薪资', ei.expected_salary);
    html += infoItem('工作年限', ei.work_years != null ? `${ei.work_years} 年` : null);
    html += '</div></div>';

    // -- Education --
    const edu = ei.education || {};
    if (edu.level || edu.school || edu.major) {
        html += '<div class="section">';
        html += '<div class="section-title">教育背景</div>';
        html += '<div class="info-grid">';
        html += infoItem('学历', edu.level);
        html += infoItem('院校', edu.school);
        html += infoItem('专业', edu.major);
        html += infoItem('毕业时间', edu.graduation_date);
        html += '</div></div>';
    }

    // -- Skills --
    if (ei.skills && ei.skills.length > 0) {
        html += '<div class="section">';
        html += '<div class="section-title">技能标签</div>';
        html += '<div class="skills-list">';
        ei.skills.forEach(s => { html += `<span class="skill-tag">${escapeHtml(s)}</span>`; });
        html += '</div></div>';
    }

    // -- Awards --
    if (ei.awards && ei.awards.length > 0) {
        html += '<div class="section">';
        html += '<div class="section-title">奖项与证书</div>';
        html += '<div class="skills-list">';
        ei.awards.forEach(s => { html += `<span class="skill-tag">${escapeHtml(s)}</span>`; });
        html += '</div></div>';
    }

    // -- Work Experience --
    if (ei.work_experience && ei.work_experience.length > 0) {
        html += '<div class="section">';
        html += '<div class="section-title">工作经历</div>';
        ei.work_experience.forEach(w => {
            const dates = [w.start_date, w.end_date].filter(Boolean).join(' - ');
            html += '<div class="project-item">';
            html += `<div class="project-name">${escapeHtml(w.company || '')}</div>`;
            html += `<div class="project-role">${escapeHtml(w.position || '')}${dates ? ' &middot; ' + escapeHtml(dates) : ''}</div>`;
            if (w.responsibilities) html += `<div class="project-desc">${escapeHtml(w.responsibilities)}</div>`;
            html += '</div>';
        });
        html += '</div>';
    }

    // -- Projects --
    if (ei.project_experience && ei.project_experience.length > 0) {
        html += '<div class="section">';
        html += '<div class="section-title">项目经历</div>';
        ei.project_experience.forEach(p => {
            html += '<div class="project-item">';
            html += `<div class="project-name">${escapeHtml(p.name || '')}</div>`;
            if (p.role) html += `<div class="project-role">${escapeHtml(p.role)}</div>`;
            if (p.description) html += `<div class="project-desc">${escapeHtml(p.description)}</div>`;
            if (p.technologies && p.technologies.length > 0) {
                html += '<div class="skills-list" style="margin-top:6px">';
                p.technologies.forEach(t => { html += `<span class="skill-tag">${escapeHtml(t)}</span>`; });
                html += '</div>';
            }
            html += '</div>';
        });
        html += '</div>';
    }

    // -- Matching --
    if (matching) {
        html += '<div class="section">';
        html += '<div class="section-title">岗位匹配度</div>';

        html += '<div style="text-align:center;margin-bottom:20px">';
        html += `<div class="match-score-circle ${scoreClass}">${Math.round(matching.match_score * 100)}%</div>`;
        html += '<div style="margin-top:8px;font-size:13px;color:var(--text-secondary)">综合匹配分数</div>';
        html += '</div>';

        html += '<div class="info-grid" style="margin-bottom:16px">';
        html += infoItem('技能匹配率', `${Math.round(matching.skill_match_rate * 100)}%`);
        html += infoItem('经验相关性', `${Math.round(matching.experience_relevance * 100)}%`);
        html += infoItem('学历匹配', matching.education_match ? '满足' : '不满足');
        html += '</div>';

        if (matching.job_keywords && matching.job_keywords.length > 0) {
            html += '<div style="margin-bottom:12px">';
            html += '<div style="font-size:13px;color:var(--text-muted);margin-bottom:6px">岗位关键词</div>';
            html += '<div class="skills-list">';
            matching.job_keywords.forEach(k => { html += `<span class="skill-tag">${escapeHtml(k)}</span>`; });
            html += '</div></div>';
        }

        if (matching.overall_feedback) {
            html += '<div style="padding:14px 16px;background:var(--bg-secondary);border-radius:var(--radius-md);margin-bottom:12px">';
            html += `<div style="font-size:13px;color:var(--text-muted);margin-bottom:4px">综合评价</div>`;
            html += `<div style="font-size:14px;color:var(--text-primary);line-height:1.6">${escapeHtml(matching.overall_feedback)}</div>`;
            html += '</div>';
        }

        if (matching.strengths && matching.strengths.length > 0) {
            html += '<div style="margin-bottom:12px">';
            html += '<div class="badge badge-success" style="margin-bottom:6px">优势</div>';
            matching.strengths.forEach(s => { html += `<div style="font-size:13px;padding:2px 0">+ ${escapeHtml(s)}</div>`; });
            html += '</div>';
        }

        if (matching.weaknesses && matching.weaknesses.length > 0) {
            html += '<div>';
            html += '<div class="badge badge-warning" style="margin-bottom:6px">不足</div>';
            matching.weaknesses.forEach(w => { html += `<div style="font-size:13px;padding:2px 0">- ${escapeHtml(w)}</div>`; });
            html += '</div>';
        }

        html += '</div>';
    }

    // -- Raw JSON toggle --
    html += '<div class="section" style="margin-top:8px">';
    html += '<button class="btn btn-outline btn-block" id="toggleJsonBtn" onclick="toggleJson()">';
    html += '查看原始 JSON 数据';
    html += '</button>';
    html += `<div class="json-viewer hidden" id="jsonViewer">${escapeHtml(JSON.stringify(data, null, 2))}</div>`;
    html += '</div>';

    $resultsBody.innerHTML = html;
}

function toggleJson() {
    const viewer = document.getElementById('jsonViewer');
    const btn = document.getElementById('toggleJsonBtn');
    if (viewer.classList.contains('hidden')) {
        viewer.classList.remove('hidden');
        btn.textContent = '隐藏原始 JSON 数据';
    } else {
        viewer.classList.add('hidden');
        btn.textContent = '查看原始 JSON 数据';
    }
}

// =========================================================================
// Helpers
// =========================================================================

function infoItem(label, value) {
    if (value === null || value === undefined || value === '') return '';
    return `<div class="info-item">
        <div class="info-item-label">${label}</div>
        <div class="info-item-value">${escapeHtml(String(value))}</div>
    </div>`;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    $toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}
