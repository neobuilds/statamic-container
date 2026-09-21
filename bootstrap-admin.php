<?php
// Deployment-only bootstrap using upstream's public facade, before serving HTTP.
require '/var/www/html/vendor/autoload.php';
$app = require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
set_exception_handler(function (Throwable $e) { fwrite(STDERR, "Administrator bootstrap failed; HTTP remains disabled.\n"); exit(1); });
$lock = fopen('/data/.bootstrap.lock', 'c');
if (!$lock || !flock($lock, LOCK_EX)) { throw new RuntimeException('Cannot lock bootstrap'); }
if (Statamic\Facades\User::query()->count() === 0) {
    $email = getenv('STATAMIC_ADMIN_EMAIL');
    $password = getenv('STATAMIC_ADMIN_PASSWORD');
    if (!filter_var($email, FILTER_VALIDATE_EMAIL) || strlen($password ?: '') < 16) {
        throw new RuntimeException('Valid admin email and password of at least 16 characters required');
    }
    Statamic\Facades\User::make()->email($email)->password($password)->makeSuper()->save();
}
flock($lock, LOCK_UN);
fclose($lock);
