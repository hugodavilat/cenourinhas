from django.shortcuts import render


def home(request):
    """Render the simple under-development homepage."""
    return render(request, 'index.html', {'message': 'Os Cenourinhas estão trabalhando'})
