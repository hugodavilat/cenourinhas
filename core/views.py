from django.shortcuts import render


def home(request):
    """Render the wedding homepage for Aline and Hugo."""
    context = {
        'bride': 'Aline',
        'groom': 'Hugo',
        'wedding_date': 'Data a confirmar',
        'venue': 'Local a confirmar',
        'address': '',
        'message': 'Estamos preparando uma celebração especial — mais informações em breve.'
    }
    return render(request, 'index.html', context)
