db = db.getSiblingDB('app_qmjfeopc');

db.createUser({
  user: 'appqmjfeopc',
  pwd: 'app123qmjfeopc',
  roles: [
    { role: 'readWrite', db: 'app_qmjfeopc' }
  ]
});

db.createCollection('__init_marker');
db.__init_marker.insertOne({ initialized: true, date: new Date() });
