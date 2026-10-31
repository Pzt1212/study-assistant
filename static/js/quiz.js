/* ============================================================
   刷题模式逻辑（支持三种题型）
   - 选择题：显示 A/B/C/D 选项按钮，单选作答 → 服务端自动判分
   - 填空题：显示输入框，文本作答 → 去首尾空白后自动判分
   - 解答题：显示文本框书写解答过程，提交后展示参考答案 +
             解析 + 评分标准，由用户自评得分（或跳过不计分）
   - 支持组合筛选：学科 / 难度 / 题型，切换后自动重新抽题
   - 更新答题统计（正确 / 错误 / 正确率）
   ============================================================ */
(function () {
  "use strict";

  // ---------- DOM 引用 ----------
  var quizBody = document.getElementById("quiz-body");
  var scoreCorrect = document.getElementById("score-correct");
  var scoreWrong = document.getElementById("score-wrong");
  var scoreAccuracy = document.getElementById("score-accuracy");
  var quizSubject = document.getElementById("quiz-subject");
  var quizSubjectSelect = document.getElementById("quiz-subject-filter");
  var quizDifficultySelect = document.getElementById("quiz-difficulty");
  var quizTypeSelect = document.getElementById("quiz-type");
  var btnReload = document.getElementById("btn-reload");

  // 题型常量（与后端 blueprints/questions.py 保持一致）
  var TYPE_CHOICE = "选择题";
  var TYPE_FILL = "填空题";
  var TYPE_ANSWER = "解答题";

  // 当前题目状态
  var currentQuestionId = null;  // 当前题目 id
  var currentType = TYPE_CHOICE; // 当前题目实际题型
  var currentAnswer = "";        // 当前题目已输入/选择的答案文本
  var answered = false;          // 是否已作答（防止重复提交）

  // 当前抽题范围（空串 = 不限）
  var typeFilter = "";
  var subjectFilter = "";
  var difficultyFilter = "";

  // 当前是否有筛选条件生效（用于空结果提示）
  function hasFilter() {
    return !!(typeFilter || subjectFilter || difficultyFilter);
  }

  // 生成带全部筛选条件的抽题 URL
  function randomUrl() {
    var params = [];
    if (subjectFilter) params.push("subject=" + encodeURIComponent(subjectFilter));
    if (difficultyFilter) params.push("difficulty=" + encodeURIComponent(difficultyFilter));
    if (typeFilter) params.push("type=" + encodeURIComponent(typeFilter));
    return "/questions/api/random" + (params.length ? "?" + params.join("&") : "");
  }

  // ---------- 抽题 ----------
  function loadQuestion() {
    quizBody.innerHTML = '<div class="quiz-loading">加载题目中…</div>';
    answered = false;
    currentQuestionId = null;
    currentAnswer = "";

    fetch(randomUrl())
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (!data.ok) {
          var emptyText = hasFilter()
            ? data.error || "没有符合筛选条件的题目，试试放宽条件。"
            : data.error || "题库为空，请先添加题目。";
          quizBody.innerHTML =
            '<div class="empty-state"><p>' + escapeHtml(emptyText) + "</p>" +
            '<p style="margin-top:10px">' +
            '<button type="button" class="btn btn-ghost" id="btn-again">再抽一次</button> ' +
            '<a href="/questions/new" class="btn btn-primary">去添加题目</a></p></div>';
          var again = document.getElementById("btn-again");
          if (again) again.addEventListener("click", loadQuestion);
          return;
        }
        renderQuestion(data.question);
      })
      .catch(function () {
        quizBody.innerHTML = '<div class="empty-state"><p>加载失败，请刷新重试。</p></div>';
      });
  }

  // 根据题型动态渲染题干与作答区
  function renderQuestion(q) {
    currentQuestionId = q.id;
    currentType = q.question_type || TYPE_CHOICE;

    // 更新顶部科目标签（纯文本，无底色）
    if (quizSubject) {
      quizSubject.textContent = q.subject;
      quizSubject.className = "quiz-subject-label";
    }

    // 题目信息行（纯文本 meta，无徽章底色）+ 题干
    var html = '';
    html += '<div class="quiz-meta">';
    html += '  <span class="q-meta">' + escapeHtml(currentType) + "</span>";
    html += '  <span class="q-meta">' + escapeHtml(q.topic || "未分类") + "</span>";
    html += '  <span class="q-meta">' + escapeHtml(q.difficulty || "中等") + "</span>";
    html += '  <span class="q-meta">' + escapeHtml(String(q.score || "")) + " 分</span>";
    html += "</div>";
    if (q.image) {
      html += '<div class="quiz-figure"><img src="' + escapeHtml(q.image) +
              '" alt="题图" loading="lazy"></div>';
    }
    html += '<div class="quiz-question">' + escapeHtml(q.content) + "</div>";

    // 按题型渲染作答控件
    if (currentType === TYPE_CHOICE) {
      html += renderChoiceArea(q.options);
    } else if (currentType === TYPE_FILL) {
      html += renderFillArea();
    } else {
      html += renderAnswerArea();
    }

    // 底部操作按钮（提交 / 下一题）
    html += '<div class="quiz-actions">' +
            '<button type="button" class="btn btn-primary" id="btn-submit">' +
            (currentType === TYPE_ANSWER ? "提交解答" : "提交答案") +
            "</button>" +
            '<button type="button" class="btn btn-ghost" id="btn-next" style="display:none">下一题</button>' +
            "</div>";

    quizBody.innerHTML = html;

    // 绑定当前题型的交互
    if (currentType === TYPE_CHOICE) {
      bindChoiceEvents();
    } else {
      // 填空题 / 解答题：回车提交（textarea 用 Ctrl+Enter）
      var input = document.getElementById("answer-input");
      if (input) {
        input.addEventListener("keydown", function (e) {
          var enter = e.key === "Enter" || e.keyCode === 13;
          if (currentType === TYPE_FILL && enter) {
            e.preventDefault();
            submitAnswer();
          } else if (currentType === TYPE_ANSWER && enter && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            submitAnswer();
          }
        });
        input.focus();
      }
    }

    document.getElementById("btn-submit").addEventListener("click", submitAnswer);
    document.getElementById("btn-next").addEventListener("click", loadQuestion);
  }

  // ---------- 三种题型的作答区渲染 ----------

  // 选择题：A/B/C/D 选项按钮
  function renderChoiceArea(options) {
    var html = '<div class="quiz-options">';
    (options || []).forEach(function (opt) {
      html +=
        '<div class="quiz-option" data-key="' + escapeHtml(opt.key) + '">' +
        '<span class="quiz-option-key">' + escapeHtml(opt.key) + "</span>" +
        "<span>" + escapeHtml(opt.text) + "</span>" +
        "</div>";
    });
    html += "</div>";
    return html;
  }

  // 选择题：点击选中（单选，可切换）
  function bindChoiceEvents() {
    var options = quizBody.querySelectorAll(".quiz-option");
    options.forEach(function (el) {
      el.addEventListener("click", function () {
        if (answered) return;
        options.forEach(function (o) { o.classList.remove("selected"); });
        el.classList.add("selected");
        document.getElementById("btn-submit").disabled = false;
      });
    });
    // 初始禁用提交按钮，选完再启用
    document.getElementById("btn-submit").disabled = true;
  }

  // 填空题：文本输入框
  function renderFillArea() {
    return '<div class="field quiz-input-row">' +
           '<label for="answer-input">你的答案</label>' +
           '<input type="text" id="answer-input" placeholder="请输入答案，回车提交" autocomplete="off">' +
           "</div>";
  }

  // 解答题：多行文本框（书写解答过程）
  function renderAnswerArea() {
    return '<div class="field quiz-input-row">' +
           '<label for="answer-input">你的解答过程</label>' +
           '<textarea id="answer-input" rows="6" placeholder="请书写解题过程（Ctrl+Enter 提交）"></textarea>' +
           "</div>";
  }

  // ---------- 提交与判分 ----------

  // 统一点击「提交」入口，按题型组装请求
  function submitAnswer() {
    if (answered) return;

    if (currentType === TYPE_CHOICE) {
      var selected = quizBody.querySelector(".quiz-option.selected");
      if (!selected) {
        alert("请先选择一个答案。");
        return;
      }
      currentAnswer = selected.dataset.key;
    } else {
      var input = document.getElementById("answer-input");
      currentAnswer = input ? input.value : "";
      if (currentType === TYPE_FILL && !currentAnswer.trim()) {
        alert("请先填写答案。");
        return;
      }
      if (currentType === TYPE_ANSWER && !currentAnswer.trim()) {
        // 解答题允许交白卷看参考答案？不允许：至少要提交（提示）
        if (!confirm("解答过程为空，确定直接查看参考答案吗？")) return;
      }
    }

    answered = true;
    disableSubmit("提交中…");

    fetch("/questions/api/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question_id: currentQuestionId,
        answer: currentAnswer,
      }),
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (!data.ok) {
          alert(data.error || "提交失败");
          answered = false;
          enableSubmit("提交答案");
          return;
        }
        if (data.answer_type === TYPE_ANSWER) {
          // 解答题：展示参考答案 / 解析 / 评分标准 + 自评控件
          showAnswerReference(data);
        } else {
          // 选择题 / 填空题：展示自动判分结果
          showAutoResult(data);
        }
        if (data.stats) updateStats(data.stats);
      })
      .catch(function () {
        alert("网络错误，请重试");
        answered = false;
        enableSubmit("提交答案");
      });
  }

  // 选择题 / 填空题的自动判分结果
  function showAutoResult(data) {
    // 选择题：绿色高亮正确项，红色高亮错选项
    if (currentType === TYPE_CHOICE) {
      var options = quizBody.querySelectorAll(".quiz-option");
      options.forEach(function (el) {
        if (el.dataset.key === data.correct_answer) {
          el.classList.add("correct");
        }
        if (el.classList.contains("selected") && !data.correct) {
          el.classList.add("wrong");
        }
      });
    }

    var box = document.createElement("div");
    box.className = "quiz-result " + (data.correct ? "ok" : "bad");
    var head = data.correct
      ? "回答正确！"
      : "回答错误，正确答案是 " + escapeHtml(data.correct_answer || "");
    box.innerHTML = "<strong>" + head + "</strong>";
    if (data.analysis) {
      box.innerHTML += '<div class="analysis">解析：' + escapeHtml(data.analysis) + "</div>";
    }
    quizBody.insertBefore(box, quizBody.querySelector(".quiz-actions"));

    // 显示「下一题」，隐藏「提交」
    document.getElementById("btn-submit").style.display = "none";
    document.getElementById("btn-next").style.display = "";
  }

  // 解答题：展示参考答案 + 解析 + 评分标准，引导自评
  function showAnswerReference(data) {
    var html = '<div class="quiz-reference">';

    html += '<div class="ref-block">';
    html += "<strong>参考答案</strong>";
    html += '<div class="pre-wrap">' + escapeHtml(data.reference_answer || "") + "</div>";
    html += "</div>";

    if (data.analysis) {
      html += '<div class="ref-block">';
      html += "<strong>解题思路 / 解析</strong>";
      html += '<div class="pre-wrap">' + escapeHtml(data.analysis) + "</div>";
      html += "</div>";
    }

    // 评分标准：step_rules 为 {步骤: 分值} 的 dict
    var rules = data.step_rules || {};
    var ruleKeys = Object.keys(rules);
    if (ruleKeys.length) {
      html += '<div class="ref-block">';
      html += "<strong>评分标准（满分 " + escapeHtml(String(data.full_score)) + " 分）</strong>";
      html += '<ul class="step-rules">';
      ruleKeys.forEach(function (step) {
        html += "<li>" + escapeHtml(step) + " —— " + escapeHtml(String(rules[step])) + " 分</li>";
      });
      html += "</ul>";
      html += "</div>";
    }

    // 自评得分控件
    html += '<div class="field self-score-row">';
    html += '<label for="self-score">对照评分标准自评得分（0 ~ ' +
            escapeHtml(String(data.full_score)) + " 分，满分视为做对）</label>";
    html += '<div class="self-score-input">' +
            '<input type="number" id="self-score" min="0" max="' +
            escapeHtml(String(data.full_score)) + '" value="0" step="1">' +
            '<button type="button" class="btn btn-primary" id="btn-grade">提交自评得分</button>' +
            "</div>";
    html += "</div>";

    html += "</div>";

    // 把参考区插到操作按钮之前
    var actions = quizBody.querySelector(".quiz-actions");
    var wrapper = document.createElement("div");
    wrapper.innerHTML = html;
    while (wrapper.firstChild) {
      quizBody.insertBefore(wrapper.firstChild, actions);
    }

    // 隐藏「提交」，显示「下一题」前的自评按钮；另提供「跳过不计分」
    document.getElementById("btn-submit").style.display = "none";
    var gradeBtn = document.getElementById("btn-grade");
    gradeBtn.addEventListener("click", submitSelfGrade);

    // 操作区补一个「跳过此题（不计分）」按钮
    var skip = document.createElement("button");
    skip.type = "button";
    skip.className = "btn btn-ghost";
    skip.id = "btn-skip";
    skip.textContent = "跳过此题（不计分）";
    actions.insertBefore(skip, actions.firstChild);
    skip.addEventListener("click", loadQuestion);
  }

  // 解答题：把自评得分提交给后端记录
  function submitSelfGrade() {
    var input = document.getElementById("self-score");
    var score = input ? parseInt(input.value, 10) : 0;
    if (isNaN(score)) {
      alert("请填写有效的自评得分。");
      return;
    }

    var gradeBtn = document.getElementById("btn-grade");
    gradeBtn.disabled = true;
    gradeBtn.textContent = "保存中…";

    fetch("/questions/api/grade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question_id: currentQuestionId,
        answer: currentAnswer,
        score: score,
      }),
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (!data.ok) {
          alert(data.error || "保存失败");
          gradeBtn.disabled = false;
          gradeBtn.textContent = "提交自评得分";
          return;
        }
        // 显示记录成功提示
        var tip = document.createElement("div");
        tip.className = "quiz-result " + (data.correct ? "ok" : "bad");
        tip.innerHTML = "<strong>自评得分 " + escapeHtml(String(data.score)) + " / " +
          escapeHtml(String(data.full_score)) + " 分，已记录（" +
          (data.correct ? "视为做对" : "视为错误") + "）。</strong>";
        quizBody.insertBefore(tip, quizBody.querySelector(".quiz-actions"));

        // 隐藏自评控件与跳过按钮，显示下一题
        var selfScoreRow = quizBody.querySelector(".self-score-row");
        if (selfScoreRow) selfScoreRow.style.display = "none";
        var skip = document.getElementById("btn-skip");
        if (skip) skip.style.display = "none";
        document.getElementById("btn-next").style.display = "";

        if (data.stats) updateStats(data.stats);
      })
      .catch(function () {
        alert("网络错误，请重试");
        gradeBtn.disabled = false;
        gradeBtn.textContent = "提交自评得分";
      });
  }

  // ---------- 工具函数 ----------

  function disableSubmit(text) {
    var btn = document.getElementById("btn-submit");
    if (btn) {
      btn.disabled = true;
      if (text) btn.textContent = text;
    }
  }

  function enableSubmit(text) {
    var btn = document.getElementById("btn-submit");
    if (btn) {
      btn.disabled = false;
      if (text) btn.textContent = text;
    }
  }

  // 更新顶部统计
  function updateStats(stats) {
    if (!stats) return;
    if (scoreCorrect) scoreCorrect.textContent = stats.correct;
    if (scoreWrong) scoreWrong.textContent = stats.wrong;
    if (scoreAccuracy) scoreAccuracy.textContent = stats.accuracy + "%";
  }

  // HTML 转义，防止题干/答案中的特殊字符破坏页面结构
  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  // ---------- 初始化 ----------

  // 切换筛选条件：学科 / 难度 / 题型，任一变化都自动重新抽题
  function bindFilter(select, setter) {
    if (!select) return;
    select.addEventListener("change", function () {
      setter(select.value);
      loadQuestion();
    });
  }
  bindFilter(quizSubjectSelect, function (v) { subjectFilter = v; });
  bindFilter(quizDifficultySelect, function (v) { difficultyFilter = v; });
  bindFilter(quizTypeSelect, function (v) { typeFilter = v; });

  // 「换一道」按钮：按当前筛选条件重新随机抽题
  if (btnReload) {
    btnReload.addEventListener("click", function () {
      loadQuestion();
    });
  }

  loadQuestion();
})();
