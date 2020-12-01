
// Автоматическое обновление времени
async function updateTime() {
    $.ajax({
        type: "POST",
        url: "/get_time"
    })
        .done(function (data) {
            var r = /\d+/;
            var s = $('.current-time').text();
            $('.current-time').text(s.replace(r, data.response))
        })
}

setInterval(updateTime, 60000);

// tippy instances
// название плейлиста -> обновить плейлист
const instance = tippy(document.querySelector('#testTippy'),{
    trigger: 'manual',
    arrow: false,
    offset: [0, 10],
    placement: 'right-end',
    duration: [100, 200],
    theme: "spotigreen",
    animation: 'scale',
    inertia: true,
});

// TODO: удалить в будущих апдейтах и заменить на что-то другое
tippy(document.querySelector('#dedupQuestion'),{
    content: $('#dedupQuestionText').val() ,
    placement: 'right-end',
    duration: [100, 200],
    inertia: true,
});

tippy(document.querySelector('#dedupFixed'),{
    content: $('#dedupFixedText').val() ,
    placement: 'right-end',
    duration: [100, 200],
    inertia: true,
});


function checkCheckbox(inputId) {
    isChecked = document.getElementById(event.target.id).checked;
    if (isChecked) {
        $('#' + inputId).addClass('reveal')
    }
    if (!isChecked) {
        $('#' + inputId).removeClass('reveal')
    }
}

// settings AJAX
$('#updateSettingsButton').click(function () {
    var gotErrors = false

    function checkInputs(item) {
        if ( $(item[0]).val() < item[1] ){
            $(item[0]).addClass('blocked')
            gotErrors = true
        }
    }

    inputIds = [['#dedupValue', 200], ['#fixedValue', 100], ['#updateTimeValue', 10]]
    inputIds.forEach(element => $(element[0]).removeClass('blocked'));
    inputIds.forEach(checkInputs)

    if (gotErrors) {
        console.log('some errors in settings')
    }
    else {
        $('#updateSettingsButton').prop('disabled', true);
        $.ajax({
            type: "POST",
            url: "/update_settings",
            dataType: 'json',
            data: {
                dedupStatus: document.getElementById("fixedDedupSwitch").checked,
                dedupValue: $('#dedupValue').val(),
                fixedStatus: document.getElementById("fixedPlaylistSwitch").checked,
                fixedValue: $('#fixedValue').val(),
                lastFmStatus: document.getElementById("lastFmSwitch").checked,
                lastFmValue: $('#lastFmValue').val(),
                updateTimeValue: $('#updateTimeValue').val(),
            },
        })
            .done(function (data) {
                $('#updateSettingsButton').prop('disabled', false);
                if (data.error){
                    $('#settingsModal .alert-danger').show()
                    $('#settingsModal .alert-danger .alertTextArea').text(data.error)
                    $('#settingsModal .alert-danger').delay(3000).fadeOut("slow")
                }
                else {
                    $('#settingsModal').modal('hide')
                    $('#settingsModal .alert-success').show()
                    $('#settingsModal .alert-success .alertTextArea').text(data.response)
                    $('#settingsModal .alert-success').delay(3000).fadeOut("slow")
                    updateTime()
                }
            })
    }
});



// update AJAX
$('#manualUpdate').click(function () {
    $('#updateSpinner').addClass('busy');
    $('#manualUpdate').prop('disabled', true);
    $.ajax({
        type: "POST",
        url: "/make_history",
        data: { update: true },
    })
        .done(function (data) {
            instance.setProps({
                content: data.response,
                });
            instance.show()
            $('#updateSpinner').removeClass('busy')
            $('#manualUpdate').prop('disabled', false);
        })
});

// create favorite AJAX
$('#manualUpdate2').click(function () {
    $('#updateSpinner2').addClass('busy');
    $('#manualUpdate2').prop('disabled', true);
    $.ajax({
        type: "POST",
        url: "/make_liked",
        data: { update: true },
    })
        .done(function (data) {
            $('#successAlert').show()
            $('#alertTextArea').text(data.response)
            $('#successAlert').delay(5000).fadeOut("slow")
            $('#updateSpinner2').removeClass('busy')
            $('#manualUpdate2').prop('disabled', false);
        })
});

// TODO: сделать общий интерфейс для объектов
// Auto-update
function autoUpdateToggle() {
    console.log(document.getElementById(event.target.id).checked)
    $.ajax({
        type: "POST",
        url: "/auto_update",
        data: { update: document.getElementById(event.target.id).checked },
    })
        .done(function (data) {
            $('#successAlert').show()
            $('#alertTextArea').text(data.response)
            $('#successAlert').delay(5000).fadeOut("slow")
        })
}

function autoUpdateToggle2() {
    console.log(document.getElementById(event.target.id).checked)
    $.ajax({
        type: "POST",
        url: "/auto_update_favorite",
        data: { update: document.getElementById(event.target.id).checked },
    })
        .done(function (data) {
            $('#successAlert').show()
            $('#alertTextArea').text(data.response)
            $('#successAlert').delay(5000).fadeOut("slow")
        })
}