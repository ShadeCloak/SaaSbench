db = db.getSiblingDB('admin');

db.createUser({
  user: 'appygamciur',
  pwd: 'app123ygamciur',
  roles: [
    { role: 'readWrite', db: 'app_ygamciur' },
    { role: 'dbAdmin', db: 'app_ygamciur' }
  ]
});

db = db.getSiblingDB('app_ygamciur');

db.createCollection('placeholder');
db.placeholder.drop();

print('Database app_ygamciur initialized with user appygamciur');
