function createNewInput() {
    element = '<div class="row mb-2"><div class="col-10 urlInput"><input list="playlists" placeholder="URL или URI плейлиста" type="text" class="form-control" onblur="isSubscribed()"></div><div class="result col"></div></div>'
    $('#inputs').append(element); 
}


function deleteInput(target) {
    $(target).remove()
}

function check_pair() {
    
    viberChecks = $('.viberCheck')
    
    for (let i = 0; i < viberChecks.length; i++) { 
        toDelete = true
        viberText = $(viberChecks[i]).text()

        $('input').each(function(){
            if ($(this).val() == viberText)  {
                toDelete = false
            }
        });

        if (toDelete){
            $('.viberCheck:contains("'+ viberText +'")').parent().hide('slow', function() {
                $(this).remove();
            })
            $('.suggestedPlaylists:contains("'+ viberText +'")').next().hide('slow')
        }
      }
}

function trimText(text){
    var output = text
    if ($(document).width() > 480) {
        if (text.length > 30) {
            text = text.slice(0, 30)
            output = text + '...'
            }
    }
    else {
        if (text.length > 16) {
        text = text.slice(0, 16)
        output = text + '...'
        }
    }
    return output
}


function request_existance(url, target) {
    $.ajax({
        type: "POST",
        url: "/playlist_worker",
        data: { url : url },
    })
    .done(function (data) {
        if (data.response){
            $(target).next().text('✔️')
            if ($('.viberCheck')[0] == undefined){
                $('.pl').show(150)
            }
            if ($('#addButton')[0] != undefined){
                $('#addButton').show()
            }
            image = data.response['images'][0]['url']
            name = data.response['name']
            element = '<div class="col-4 col-md-2"><img class="mb-0 img-fluid rounded" src="' 
                + image + 
                '"><p class="playlist-title">'+ trimText(name) +'</p><div class="viberCheck" style="display: none">'+ url +'</div></div>'
            $('.toBeAdded').append(element);
            $(element).show('slow')
        }
        else {
            $(target).next().text('❌')
        }
        check_pair()
    })
}


function isSubscribed() {
    url = event.target.value
    target = event.target
    target = $(target).parent()
    check_pair()
    if (!url){
        $(target).next().text('')
    }
    
    else if ($('.viberCheck:contains("'+ url +'")')[0] != undefined){
        console.log('nothing')
    } 
    else {
        request_existance(url, target)
    }  
}

function togglePlaylistSelect(){
    checkIconTarget = $(event.target).next().next().next()
    url = $(event.target).next().next().text()
    if ($(checkIconTarget).css('display') == 'none')
    {
        $(checkIconTarget).show(300)
        // проверка на доп. поле
        inputs = $('.urlInput')
        for (let i = 0; i < inputs.length; i++) { 
            if ($(inputs[i]).children().val() == ''){
                $(inputs[i]).children().val(url)
                target = $(inputs[i])
                request_existance(url, $(inputs[i]))

                // если есть лишее поле, то новое не создаётся
                freeSlot = false
                for (let i = 0; i < inputs.length; i++){
                    if ($(inputs[i]).children().val() == ''){
                        freeSlot = true
                    }
                }
                // иначе создаётся
                if (!freeSlot){
                    createNewInput()
                }
                break
            }
        }
    }
    else {
        $(checkIconTarget).hide(300)
        for (let i = 0; i < inputs.length; i++){
            if ($(inputs[i]).children().val() == url){
                deleteInput($(inputs[i]).parent())
            }
            check_pair()
        }
    }
}

function addUsedToSmart(){
    //$('#createSpinner').addClass('busy');
    $(event.target).prop('disabled', true);
    urls = $('.urlInput')
    arr = []
    for (let i = 0; i < urls.length; i++) { 
        url = $(urls[i]).children().val()
        if (url){
            arr.push(url)
        }
        }
    output = arr.join(';')
    $.ajax({
        type: "POST",
        url: "/playlist_worker",
        data: { addUrlToSmart : output },
    })
    .done(function (data) {
        document.location.href = '/smart_settings'
    })
}

function trimTitles(max, classname, mobile=false){
    target = $(classname)
    for (let i = 0; i < target.length; i++) {
        if ($(target[i]).text().length > max ){
            oldText = $(target[i]).text()
            newText = oldText.slice(0, max - 3) + "..."
            $(target[i]).text(newText)
            if (mobile){
                $(target[i]).css('font-size', '15px')
            }
        }
    }
}